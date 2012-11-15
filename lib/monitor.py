#!/usr/bin/env python
import sys
import time
import logging
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.events import EVENT_TYPE_MOVED, EVENT_TYPE_DELETED, EVENT_TYPE_CREATED, EVENT_TYPE_MODIFIED

class FSEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        """Catch-all event handler.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`FileSystemEvent`
        """
        if not '.gut' in event.src_path:
            if event.is_directory:
                print '%s %s' % (EVENT_TYPE_CREATED, event.src_path)
            else:
                if event.event_type == EVENT_TYPE_MOVED:
                    print '%s %s' % (EVENT_TYPE_DELETED, event.src_path)
                    print '%s %s' % (EVENT_TYPE_CREATED, event.dest_path)
                else:
                    print '%s %s' % (event.event_type, event.src_path)
            sys.stdout.flush()

if __name__ == "__main__":
    from setproctitle import setproctitle
    setproctitle('gutsmon')
    time.sleep(0.1)
    observer = Observer()
    observer.schedule(FSEventHandler(), path=sys.argv[1], recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
