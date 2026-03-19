import sys
import threading
import itertools


class Spinner:
    def __init__(self, message: str, title: str | None = None) -> None:
        self._message = message
        self._title = title
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Spinner":
        if self._title:
            sys.stderr.write(f"\n{self._title}\n\n")
            sys.stderr.flush()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        # Clear spinner line and title (move up 2 lines if title was shown)
        if self._title:
            sys.stderr.write("\r\033[K\033[1A\033[K\033[1A\033[K\033[1A\033[K")
        else:
            sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def update(self, message: str) -> None:
        self._message = message

    def _spin(self) -> None:
        for frame in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop.is_set():
                break
            sys.stderr.write(f"\r\033[K{frame} {self._message}")
            sys.stderr.flush()
            self._stop.wait(0.08)
