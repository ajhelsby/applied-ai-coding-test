import os
import signal
import time

running = True


def _handle_signal(signum: int, _frame: object) -> None:
    global running
    running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log_level = os.getenv("LOG_LEVEL", "INFO")
    print(f"orchestrator started (LOG_LEVEL={log_level})", flush=True)

    while running:
        time.sleep(1)

    print("orchestrator stopped", flush=True)


if __name__ == "__main__":
    main()
