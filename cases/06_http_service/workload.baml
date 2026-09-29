function handle(req: baml.http.Request) -> baml.http.Response throws never {
    let body = "{\"error\":\"not_found\"}";
    let status = 404;
    if (req.method == "GET" && req.url == "/health") { body = "42"; status = 200; }
    if (req.method == "POST" && req.url == "/aggregate") {
        body = run(prepare(req.body));
        status = 200;
        if (body == "{\"error\":\"invalid\"}") { status = 400; }
    }
    baml.http.Response.new(status, {"content-type":"application/json", "connection":"close"}, body.to_utf8())
}
function main() -> void {
    let addr = baml.io.input(null);
    let server = baml.http.Server.bind(addr);
    baml.io.println("@ready");
    let task = spawn { server.serve(handle, allow_http2 = false) };
    baml.io.input(null);
    task.cancel();
    (await task) catch (_) { baml.panics.Cancelled => null };
}
