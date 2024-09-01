from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import signal
import subprocess
import time
import sys

def start_bot():
  python_executable = sys.executable  # Получаем путь к текущему интерпретатору Python
  if os.name == 'nt':
    return subprocess.Popen([python_executable, 'main.py'], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
  else:
    return subprocess.Popen([python_executable, 'main.py'], preexec_fn=os.setsid)

class ChangeHandler(FileSystemEventHandler):
  def __init__(self, process):
    self.process = process

  def on_modified(self, event):
    if event.src_path.endswith(".py"):
      print(f'{event.src_path} has been modified')
      if self.process:
        try:
          if os.name == 'nt':
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
          else:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except Exception as e:
          print(f"Error terminating process: {e}")
        self.process = start_bot()

if __name__ == "__main__":
  process = start_bot()
  event_handler = ChangeHandler(process)
  observer = Observer()
  observer.schedule(event_handler, path='.', recursive=True)
  observer.start()
  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    observer.stop()
  observer.join()