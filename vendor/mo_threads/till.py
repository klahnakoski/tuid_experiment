# encoding: utf-8
#
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Author: Kyle Lahnakoski (kyle@lahnakoski.com)
#
# THIS THREADING MODULE IS PERMEATED BY THE please_stop SIGNAL.
# THIS SIGNAL IS IMPORTANT FOR PROPER SIGNALLING WHICH ALLOWS
# FOR FAST AND PREDICTABLE SHUTDOWN AND CLEANUP OF THREADS

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from time import sleep, time
from weakref import ref

from mo_future import allocate_lock as _allocate_lock
from mo_future import text_type

from mo_threads.signal import Signal

DEBUG = False
INTERVAL = 0.1


class Till(Signal):
    """
    TIMEOUT AS A SIGNAL
    """
    __slots__ = []

    locker = _allocate_lock()
    next_ping = time()
    done = Signal("Timers shutdown")
    enabled = False
    new_timers = []

    def __new__(cls, till=None, timeout=None, seconds=None):
        if not Till.enabled:
            return Till.done
        elif till == None and timeout == None and seconds == None:
            return None
        else:
            return object.__new__(cls)

    def __init__(self, till=None, timeout=None, seconds=None):
        now = time()
        if till != None:
            if not isinstance(till, (float, int)):
                from mo_logs import Log

                Log.error("Date objects for Till are no longer allowed")
            timeout = till
        elif seconds != None:
            timeout = now + seconds
        elif timeout != None:
            if not isinstance(timeout, (float, int)):
                from mo_logs import Log

                Log.error("Duration objects for Till are no longer allowed")

            timeout = now + timeout
        else:
            from mo_logs import Log
            Log.error("Should not happen")

        Signal.__init__(self, name=text_type(timeout))

        with Till.locker:
            if timeout != None:
                Till.next_ping = min(Till.next_ping, timeout)
            Till.new_timers.append((timeout, ref(self)))


Till.done.go()


def daemon(please_stop):
    from mo_logs import Log

    Till.enabled = True
    sorted_timers = []

    try:
        while not please_stop:
            now = time()

            with Till.locker:
                later = Till.next_ping - now

            if later > 0:
                try:
                    sleep(min(later, INTERVAL))
                except Exception as e:
                    from mo_logs import Log

                    Log.warning(
                        "Call to sleep failed with ({{later}}, {{interval}})",
                        later=later,
                        interval=INTERVAL,
                        cause=e
                    )
                continue

            with Till.locker:
                Till.next_ping = now + INTERVAL
                new_timers, Till.new_timers = Till.new_timers, []

            if DEBUG and new_timers:
                if len(new_timers) > 5:
                    Log.note("{{num}} new timers", num=len(new_timers))
                else:
                    Log.note("new timers: {{timers}}", timers=[t for t, _ in new_timers])

            sorted_timers.extend(new_timers)

            if sorted_timers:
                sorted_timers.sort(key=actual_time)
                for i, rec in enumerate(sorted_timers):
                    t = actual_time(rec)
                    if now < t:
                        work, sorted_timers = sorted_timers[:i], sorted_timers[i:]
                        Till.next_ping = min(Till.next_ping, sorted_timers[0][0])
                        break
                else:
                    work, sorted_timers = sorted_timers, []

                if work:
                    DEBUG and Log.note(
                            "done: {{timers}}.  Remaining {{pending}}",
                            timers=[t for t, s in work] if len(work) <= 5 else len(work),
                            pending=[t for t, s in sorted_timers] if len(sorted_timers) <= 5 else len(sorted_timers)
                        )

                    for t, r in work:
                        s = r()
                        if s is not None:
                            s.go()

    except Exception as e:
        Log.warning("unexpected timer shutdown", cause=e)
    finally:
        DEBUG and Log.alert("TIMER SHUTDOWN")
        Till.enabled = False
        # TRIGGER ALL REMAINING TIMERS RIGHT NOW
        with Till.locker:
            new_work, Till.new_timers = Till.new_timers, []
        for t, s in new_work + sorted_timers:
            s.go()

def actual_time(rec):
    return 0 if rec[1]() is None else rec[0]
