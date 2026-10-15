"""Loopback-only aMQTT lab broker. No production deployment dependency."""
from __future__ import annotations

import asyncio
import threading


class DemoBroker:
    def __init__(self, port=0):
        self.port = port
        self.loop = None
        self.broker = None
        self.error = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="linklab-lab-broker", daemon=True)

    def _run(self):
        try:
            from amqtt.broker import Broker
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            async def start():
                self.broker = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{self.port}"}},
                                      "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}})
                await self.broker.start()
                self.port = self.broker._servers["default"].instance.sockets[0].getsockname()[1]

            self.loop.run_until_complete(start())
            self.ready.set()
            self.loop.run_forever()
        except BaseException as exc:
            self.error = exc
            self.ready.set()
        finally:
            if self.loop:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.close()

    def __enter__(self):
        self.thread.start()
        if not self.ready.wait(15):
            raise RuntimeError("Lab MQTT broker startup timed out")
        if self.error:
            raise RuntimeError(f"Lab MQTT broker failed: {self.error}. Install the demo extra: pip install -e '.[demo]'") from self.error
        return self

    def __exit__(self, *_args):
        if self.loop and self.broker and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop).result(timeout=10)
            finally:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join(timeout=10)
