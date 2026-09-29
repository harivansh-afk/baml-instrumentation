#define _DEFAULT_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static void burn(clockid_t clock, long duration_ns) {
    struct timespec start, now;
    clock_gettime(clock, &start);
    do {
        clock_gettime(clock, &now);
    } while ((now.tv_sec - start.tv_sec) * 1000000000L + now.tv_nsec - start.tv_nsec < duration_ns);
}

static void *worker(void *unused) {
    (void)unused;
    burn(CLOCK_THREAD_CPUTIME_ID, 75000000);
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "sleep")) {
        usleep(150000);
    } else if (!strcmp(argv[1], "cpu")) {
        burn(CLOCK_PROCESS_CPUTIME_ID, 150000000);
    } else if (!strcmp(argv[1], "threads")) {
        pthread_t first, second;
        if (pthread_create(&first, NULL, worker, NULL) || pthread_create(&second, NULL, worker, NULL)) return 3;
        pthread_join(first, NULL);
        pthread_join(second, NULL);
    } else if (!strcmp(argv[1], "memory")) {
        size_t size = 32 * 1024 * 1024;
        volatile char *memory = malloc(size);
        if (!memory) return 3;
        for (size_t i = 0; i < size; i += 4096) memory[i] = 42;
        usleep(40000);
        free((void *)memory);
    } else if (!strcmp(argv[1], "tree")) {
        pid_t child = fork();
        if (child < 0) return 3;
        if (!child) {
            execl(argv[0], argv[0], "cpu", NULL);
            _exit(4);
        }
        wait(NULL);
    } else if (!strcmp(argv[1], "timeout")) {
        sleep(10);
    } else {
        return 7;
    }
    return 0;
}
