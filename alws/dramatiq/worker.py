from dramatiq.worker import Worker

from alws.dramatiq import rabbitmq_broker


def main():
    worker = Worker(
        broker=rabbitmq_broker,
        worker_threads=1
    )
    worker.start()


if __name__ == '__main__':
    main()
