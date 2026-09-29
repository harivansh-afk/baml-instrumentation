#!/usr/bin/env python3
"""Linux baseline harness. Run through uv; see README.txt for measurement scope."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import select
import shutil
import signal
import socket
import subprocess
import sys
import time

from fixtures import CASES, checks, encode, fixture, matches, oracle

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / '.build'
SOURCE = next((p/'baml' for p in ROOT.parents if (p/'baml/.git').exists()), None)
LIBC = ctypes.CDLL(None, use_errno=True)
LANGUAGES = ('baml', 'rust', 'go', 'python', 'node')
EXT = {'baml': 'baml', 'rust': 'rs', 'go': 'go', 'python': 'py', 'node': 'ts', 'bun': 'ts'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, *, env=None, cwd=ROOT):
    p = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, timeout=110)
    if p.returncode:
        raise RuntimeError(f'{args}:\n{p.stdout}\n{p.stderr}')
    return p.stdout.strip()


def environment(mode):
    return dict(os.environ, BAML_TELEMETRY=mode, BAML_CLI_ALLOW_DIRECT='1',
                BAML_AGENT_SKILL_CHECK='off', BAML_TELEMETRY_DISABLED='1', DO_NOT_TRACK='1',
                BAML_HOME=str(BUILD / 'baml-home'), BAML_CACHE_DIR=str(BUILD / 'baml-cache'))


def sources(case, lang):
    paths = [ROOT / case / f'workload.{EXT[lang]}']
    if case == '06_http_service':
        paths.append(ROOT / '03_json_aggregate' / f'workload.{EXT[lang]}')
    else:
        paths.append(ROOT / 'drivers' / f'main.{EXT[lang]}')
    if lang == 'rust': paths.append(ROOT/'Cargo.toml')
    if lang in ('node','bun'): paths.append(ROOT/'package.json')
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def build(args):
    BUILD.mkdir(exist_ok=True)
    manifest_path = BUILD / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    # Cargo's declared paths must all exist, even when selecting a single bin.
    for case in CASES:
        dest = BUILD / 'rust' / case
        dest.mkdir(parents=True, exist_ok=True)
        if case == '06_http_service':
            shutil.copyfile(ROOT / case / 'workload.rs', dest / 'main.rs')
            shutil.copyfile(ROOT / '03_json_aggregate/workload.rs', dest / 'aggregate.rs')
        else:
            shutil.copyfile(ROOT / 'drivers/main.rs', dest / 'main.rs')
            shutil.copyfile(ROOT / case / 'workload.rs', dest / 'workload.rs')
    for lang in args.languages:
        if lang == 'rust':
            cmd = ['cargo', 'build', '--release', '--manifest-path', str(ROOT / 'Cargo.toml'),
                   '--target-dir', str(BUILD / 'target')]
            for case in args.cases: cmd += ['--bin', case]
            command(cmd)
            version = command(['rustc', '--version'])
        elif lang == 'go': version = command(['go', 'version'])
        elif lang in ('node', 'bun'): version = command([lang, '--version'])
        elif lang == 'python': version = sys.version
        else:
            if not args.baml: raise ValueError('build --baml needs the exact BAML compiler executable')
            version = command([args.baml, '--version'], env=environment('off'))
        for case in args.cases:
            src = ROOT / case / f'workload.{EXT[lang]}'
            if lang == 'baml':
                merged = BUILD / f'{case}.baml'
                if case == '06_http_service':
                    content = (ROOT / '03_json_aggregate/workload.baml').read_text() + src.read_text()
                else: content = src.read_text() + '\n' + (ROOT / 'drivers/main.baml').read_text()
                merged.write_text(content)
                binary = BUILD / case
                command([args.baml, 'pack', 'main', '--file', str(merged), '-o', str(binary)], env=environment('off'))
                invocation = [str(binary)]
            elif lang == 'go':
                dest = BUILD / 'go' / case
                dest.mkdir(parents=True, exist_ok=True)
                if case == '06_http_service':
                    shutil.copyfile(src, dest / 'main.go')
                    shutil.copyfile(ROOT / '03_json_aggregate/workload.go', dest / 'workload.go')
                else:
                    shutil.copyfile(ROOT / 'drivers/main.go', dest / 'main.go')
                    shutil.copyfile(src, dest / 'workload.go')
                binary = dest / 'program'
                command(['go', 'build', '-trimpath', '-ldflags=-s -w', '-o', str(binary), str(dest/'main.go'), str(dest/'workload.go')])
                invocation = [str(binary)]
            elif lang == 'rust': invocation = [str(BUILD / 'target/release' / case)]
            else:
                interpreter = sys.executable if lang == 'python' else shutil.which(lang)
                if not interpreter: raise ValueError(f'{lang} unavailable')
                if case == '06_http_service':
                    if lang == 'python':
                        interpreter = str(BUILD / 'python-http/bin/python')
                        if not Path(interpreter).exists():
                            command(['uv', 'venv', '--python', sys.executable, str(BUILD/'python-http')])
                        command(['uv', 'pip', 'install', '--python', interpreter, 'aiohttp==3.12.15'])
                    invocation = [interpreter, str(src), str(ROOT/'03_json_aggregate'/f'workload.{EXT[lang]}')]
                else: invocation = [interpreter, str(ROOT/'drivers'/f'main.{EXT[lang]}'), str(src)]
            record = {'command': invocation, 'version': version, 'source_hashes': sources(case, lang),
                      'executable_sha256': digest(invocation[0]), 'executable_bytes': Path(invocation[0]).stat().st_size}
            if lang == 'rust': record['cargo_lock_sha256'] = digest(ROOT/'Cargo.lock')
            if lang == 'rust': record['build_flags'] = 'cargo build --release; profile in hashed Cargo.toml'
            if lang == 'go': record['build_flags'] = 'go build -trimpath -ldflags="-s -w"; default optimization'
            if lang == 'node': record['runtime_versions'] = json.loads(command([invocation[0],'-p','JSON.stringify(process.versions)']))
            if lang == 'python' and case == '06_http_service':
                record['packages'] = command(['uv','pip','freeze','--python',invocation[0]]).splitlines()
            if lang == 'baml':
                record.update(compiler=str(Path(args.baml).resolve()), compiler_sha256=digest(args.baml),
                              runtime_revision=args.baml_revision or 'unknown; do not infer from source checkout',
                              packaging='baml pack: bytecode plus VM, NOT AOT Rust output',
                              telemetry_sink='packed runtime default local sink; verify recordings separately')
            manifest[f'{case}/{lang}'] = record
            manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
            print(f'built {case}/{lang}', flush=True)


def proc_sample(pid):
    """Process CPU clock includes every thread; keep coarse ticks as a cross-check."""
    stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    ticks = os.sysconf('SC_CLK_TCK')
    clock_id = ctypes.c_int()
    error = LIBC.clock_getcpuclockid(pid, ctypes.byref(clock_id))
    if error: raise ProcessLookupError(error, 'clock_getcpuclockid')
    return {'cpu_s': time.clock_gettime_ns(clock_id.value) / 1e9,
            'cpu_s_ticks': (int(stat[11]) + int(stat[12])) / ticks,
            'rss_bytes': int(stat[21]) * os.sysconf('SC_PAGE_SIZE')}


def observer():
    binary = BUILD/'observer'
    source = ROOT/'observer.c'
    if not binary.exists() or source.stat().st_mtime_ns > binary.stat().st_mtime_ns:
        BUILD.mkdir(exist_ok=True)
        command(['cc','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)])
    return str(binary)


class Child:
    def __init__(self, record, initial, mode, directory, timeout=110):
        directory.mkdir(parents=True, exist_ok=False)
        self.stderr_path = directory / 'stderr.txt'
        self.stderr = self.stderr_path.open('wb')
        self.usage_path = directory/'usage.json'
        pid_path = directory/'pid.txt'
        executable = observer()
        self.start = time.perf_counter()
        self.deadline = self.start + timeout
        self.p = subprocess.Popen([executable, str(pid_path), str(self.usage_path), str(directory),
                                  ','.join(map(str, record.get('cpu_affinity', []))) or 'inherit',
                                  *record['command']], cwd=directory, env=environment(mode),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                  start_new_session=True)
        self.buffer = b''
        self.samples = []
        self.last_sample = 0.0
        self.first_result_s = None
        while not pid_path.exists() or not pid_path.read_text().strip():
            if self.p.poll() is not None or time.perf_counter() > self.deadline:
                raise RuntimeError(f'observer failed: {self.stderr_path.read_text()}')
            time.sleep(0.001)
        self.measure_pid = int(pid_path.read_text())
        self.send(initial)

    def sample(self):
        now = time.perf_counter()
        try:
            value = dict(t_s=now-self.start, **proc_sample(self.measure_pid))
            self.samples.append(value)
            self.last_sample = now
            return value
        except (FileNotFoundError, ProcessLookupError, OSError):
            return None

    def send(self, value):
        self.p.stdin.write((str(value)+'\n').encode())
        self.p.stdin.flush()

    def line(self):
        while b'\n' not in self.buffer:
            if time.perf_counter() > self.deadline: raise TimeoutError('child exceeded 110s')
            if time.perf_counter() - self.last_sample >= 0.005: self.sample()
            if select.select([self.p.stdout], [], [], 0.005)[0]:
                data = os.read(self.p.stdout.fileno(), 65536)
                if not data: raise RuntimeError(f'child stdout closed: {self.stderr_path.read_text()[-4000:]}')
                self.buffer += data
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line.decode()

    def ready(self):
        line = self.line()
        if line != '@ready': raise RuntimeError(f'protocol: expected @ready, got {line[:300]}')
        return time.perf_counter()-self.start

    def batch(self, count, expected):
        before = self.sample()
        start = time.perf_counter()
        self.send(count)
        values, arrivals = [], []
        for _ in range(count):
            line = self.line()
            if not line.startswith('@result '): raise RuntimeError(f'protocol: {line[:300]}')
            if self.first_result_s is None: self.first_result_s = time.perf_counter()-self.start
            values.append(line[8:])
            arrivals.append(time.perf_counter()-start)
        if self.line() != '@done': raise RuntimeError('missing @done')
        elapsed = time.perf_counter()-start
        after = self.sample()
        # Parse and validate after the timed batch, never pace the child on the oracle.
        for value in values:
            if not matches(json.loads(value), expected):
                raise AssertionError(f'wrong output: {value[:400]}; expected {str(expected)[:400]}')
        return {'jobs': count, 'wall_s': elapsed, 'cpu_s': after['cpu_s']-before['cpu_s'],
                'cpu_s_ticks': after['cpu_s_ticks']-before['cpu_s_ticks'],
                'completion_offsets_s': arrivals, 'correct': True}

    def finish(self):
        shutdown_start = time.perf_counter()
        self.send(0)
        self.p.stdin.close()
        # wait4 owns reaping so rusage is per child, not a global children counter.
        while True:
            pid, status, usage = os.wait4(self.p.pid, os.WNOHANG)
            if pid: break
            if time.perf_counter() > self.deadline: raise TimeoutError('child shutdown exceeded 110s')
            self.sample()
            if select.select([self.p.stdout], [], [], 0.005)[0]: os.read(self.p.stdout.fileno(), 65536)
        self.p.returncode = os.waitstatus_to_exitcode(status)
        self.stderr.close()
        self.p.stdout.close()
        if self.p.returncode: raise RuntimeError(f'child exit {self.p.returncode}: {self.stderr_path.read_text()[-4000:]}')
        diagnostic = self.stderr_path.read_text()
        if 'telemetry recording failed' in diagnostic.lower(): raise RuntimeError(diagnostic)
        usage = json.loads(self.usage_path.read_text())
        return {'wall_s': time.perf_counter()-self.start, 'cpu_s': usage['user_cpu_s']+usage['system_cpu_s'],
                **usage,
                'first_correct_result_s': self.first_result_s,
                'shutdown_wall_s': time.perf_counter()-shutdown_start, 'samples': self.samples}

    def abort(self):
        if self.p.returncode is None:
            try: os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.p.wait()
        self.p.stdin.close()
        self.p.stdout.close()
        self.stderr.close()


def load_record(case, lang):
    manifest = json.loads((BUILD/'manifest.json').read_text())
    record = manifest[f'{case}/{lang}']
    if record['source_hashes'] != sources(case, lang) or record['executable_sha256'] != digest(record['command'][0]):
        raise RuntimeError(f'stale build: rebuild {case}/{lang}')
    if lang == 'rust' and record['cargo_lock_sha256'] != digest(ROOT/'Cargo.lock'):
        raise RuntimeError('Cargo.lock changed: rebuild Rust')
    return record


def metadata(args):
    return {'schema': 1, 'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'argv': sys.argv, 'platform': platform.platform(), 'machine': platform.machine(),
            'cpu_affinity': sorted(os.sched_getaffinity(0)), 'cpu_tick_s': 1/os.sysconf('SC_CLK_TCK'),
            'cpuinfo': Path('/proc/cpuinfo').read_text(),
            'env': {k: os.environ.get(k) for k in ('GOGC','GOMEMLIMIT','GOMAXPROCS','NODE_OPTIONS','TOKIO_WORKER_THREADS','RUSTFLAGS')},
            'source_checkout_head': command(['git','-C',str(SOURCE),'rev-parse','HEAD']),
            'source_checkout_dirty': bool(command(['git','-C',str(SOURCE),'status','--porcelain'])),
            'note': 'checkout revision describes source references, not binary provenance',
            'runner_sha256': digest(__file__), 'fixtures_sha256': digest(ROOT/'fixtures.py')}


def execute(args):
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'metadata.json').write_text(json.dumps(metadata(args), indent=2)+'\n')
    jobs = []
    for case in args.cases:
        if args.action == 'verify': inputs = list(checks(case))
        else:
            raw = Path(args.input).read_text().removesuffix('\n') if args.input else fixture(case, args.size, args.variant, args.batches, args.retain, args.fanout, args.delay_ms, args.seed)
            if '\n' in raw or '\r' in raw:
                raise ValueError('--input must contain one JSON line (the protocol uses newline framing)')
            inputs = [('selected', raw)]
        for lang in args.languages:
            modes = args.telemetry if lang == 'baml' else ['none']
            for mode in modes:
                for label, raw in inputs:
                    for repeat in range(args.trials): jobs.append((case,lang,mode,label,raw,repeat))
    random.Random(args.seed).shuffle(jobs)
    results = out/'samples.jsonl'
    for index, (case,lang,mode,label,raw,repeat) in enumerate(jobs):
        record = load_record(case,lang)
        expected = oracle(case,raw)
        run_dir = out/f'{index:04d}-{case}-{lang}-{mode}-{label}'
        base = {'case':case,'language':lang,'telemetry':mode,'fixture_label':label,'trial':repeat,
                'input_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'input_bytes':len(raw.encode()), 'build':record}
        child = None
        try:
            if case == '06_http_service':
                from service import measure
                result = measure(record,raw,expected,mode,run_dir,args)
            else:
                child = Child(record,raw,mode,run_dir)
                ready = child.ready()
                warmup = child.batch(args.warmup,expected) if args.warmup else None
                measured = child.batch(args.jobs,expected)
                invocation = child.finish()
                result = {'ready_s':ready,'warmup':warmup,'batch':measured,'invocation':invocation}
            (run_dir/'input.json').write_text(raw+'\n')
            (run_dir/'expected.json').write_text(encode(expected)+'\n')
            if lang == 'baml':
                files = [p for p in (run_dir/'.baml').rglob('*') if p.is_file()]
                result['telemetry_evidence'] = {
                    'policy_verified': False,
                    'run_local_files': len(files),
                    'run_local_bytes': sum(p.stat().st_size for p in files),
                    'scope': 'only this run directory; event completeness and external sinks unverified'}
            base.update(status='valid', **result)
            if 'http' in result and result['http']['failed_or_incorrect']:
                print(f'RECORDED {case}/{lang}/{mode}: {result["http"]["failed_or_incorrect"]} failed/incorrect requests',flush=True)
            else:
                print(f'PASS {case}/{lang}/{mode}/{label} trial={repeat}',flush=True)
        except Exception as error:
            if child: child.abort()
            base.update(status='invalid',error=str(error))
            with results.open('a') as f: f.write(json.dumps(base)+'\n')
            raise
        with results.open('a') as f: f.write(json.dumps(base)+'\n')
    print(f'Raw results: {results}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('build','verify','run'))
    p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES))
    p.add_argument('--languages',nargs='+',choices=(*LANGUAGES,'bun'),default=list(LANGUAGES))
    p.add_argument('--baml',type=lambda s:str(Path(s).resolve()))
    p.add_argument('--baml-revision',help='actual runtime build revision, only if known')
    p.add_argument('--output',default=f'results/{time.strftime("%Y%m%dT%H%M%S")}-{os.getpid()}')
    p.add_argument('--input',help='one single-line JSON fixture; payload bytes preserved')
    p.add_argument('--telemetry',nargs='+',choices=('medium','off'),default=['medium','off'])
    p.add_argument('--trials',type=int,default=1)
    p.add_argument('--jobs',type=int,default=3)
    p.add_argument('--warmup',type=int,default=1)
    p.add_argument('--size',type=int,default=1024)
    p.add_argument('--variant',choices=('iterator','indexed','build','random','sorted','reverse','duplicates'),default='iterator')
    p.add_argument('--batches',type=int,default=64)
    p.add_argument('--retain',type=int,default=4)
    p.add_argument('--fanout',type=int,default=8)
    p.add_argument('--delay-ms',type=int,default=10)
    p.add_argument('--seed',type=int,default=1729)
    p.add_argument('--rate',type=float,default=20,help='HTTP scheduled requests/sec')
    p.add_argument('--requests',type=int,default=100)
    p.add_argument('--deadline-ms',type=float,default=1000,help='experimental goodput deadline, not an SLA')
    args = p.parse_args()
    if platform.system() != 'Linux': p.error('OS CPU/RSS sampler currently supports Linux only')
    for name in ('trials','jobs','requests'):
        if getattr(args,name) <= 0: p.error(f'{name} must be positive')
    for name in ('warmup','size','batches','retain','fanout','delay_ms'):
        if getattr(args,name) < 0: p.error(f'{name} must be nonnegative')
    if args.rate <= 0 or args.deadline_ms <= 0: p.error('rate and deadline must be positive')
    if args.action == 'build': build(args)
    else: execute(args)


if __name__ == '__main__': main()
