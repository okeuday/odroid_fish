#!/usr/bin/env python
#-*-Mode:python;coding:utf-8;tab-width:4;c-basic-offset:4;indent-tabs-mode:()-*-
# ex: set ft=python fenc=utf-8 sts=4 ts=4 sw=4 et:
#
# MIT License
#
# Copyright (c) 2015-2020 Michael Truog <mjtruog at protonmail dot com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#

# pylint: disable=wrong-import-position
# pylint: disable=wrong-import-order
import sys
sys.path.append('/usr/local/lib/cloudi-2.0.1/api/python/')
from cloudi import API, TerminateException
import threading
import traceback
import json
import struct
import time
import random
from timeit import default_timer

class LakeState(object):
    position = None
    rows = 2
    columns = 16
    frames = {
        0: [],
        1: [],
        2: [],
        3: [],
    }

    @staticmethod
    def set_position(prefix):
        path = prefix.split('/')
        assert len(path) == 5 # '/odroid/fish/#/'
        assert '/'.join(path[0:3]) == '/odroid/fish'
        # positioning is based on 4 numbers:
        # X(max)                  X/Y (min)
        #           2        0
        #
        #           3        1
        #                           Y (max)
        LakeState.position = int(path[3])

    @staticmethod
    def prefix(position):
        return '/odroid/fish/%d/' % position

    @staticmethod
    def x_boundary_min():
        return 0

    @staticmethod
    def x_boundary_max():
        return LakeState.columns * 2 - 1

    @staticmethod
    def y_boundary_min():
        return 0

    @staticmethod
    def y_boundary_max():
        return LakeState.rows * 2 - 1

    @staticmethod
    def x_min(position=None):
        if position is None:
            position = LakeState.position
        return {
            0: LakeState.columns * 0,
            1: LakeState.columns * 0,
            2: LakeState.columns * 1,
            3: LakeState.columns * 1,
        }[position]

    @staticmethod
    def x_max(position=None):
        if position is None:
            position = LakeState.position
        return {
            0: LakeState.columns * 1 - 1,
            1: LakeState.columns * 1 - 1,
            2: LakeState.columns * 2 - 1,
            3: LakeState.columns * 2 - 1,
        }[position]

    @staticmethod
    def y_min(position=None):
        if position is None:
            position = LakeState.position
        return {
            0: LakeState.rows * 0,
            1: LakeState.rows * 1,
            2: LakeState.rows * 0,
            3: LakeState.rows * 1,
        }[position]

    @staticmethod
    def y_max(position=None):
        if position is None:
            position = LakeState.position
        return {
            0: LakeState.rows * 1 - 1,
            1: LakeState.rows * 2 - 1,
            2: LakeState.rows * 1 - 1,
            3: LakeState.rows * 2 - 1,
        }[position]

    @staticmethod
    def xy_local(x_lake, y_lake):
        y_size = LakeState.rows * 1
        x_size = LakeState.columns * 1
        if x_lake <= (LakeState.columns * 1 - 1):
            if y_lake <= (LakeState.rows * 1 - 1):
                return (0, x_lake, y_lake)
            elif y_lake <= (LakeState.rows * 2 - 1):
                return (1, x_lake, y_lake - y_size)
        elif x_lake <= (LakeState.columns * 2 - 1):
            if y_lake <= (LakeState.rows * 1 - 1):
                return (2, x_lake - x_size, y_lake)
            elif y_lake <= (LakeState.rows * 2 - 1):
                return (3, x_lake - x_size, y_lake - y_size)
        return (None, None, None)

    @staticmethod
    def __printable_frame(frame, x_size=None):
        if x_size is None:
            x_size = LakeState.x_boundary_max() - LakeState.x_boundary_min() + 1
        rows = []
        for x_lake in range(0, len(frame), x_size):
            row = frame[x_lake:x_lake + x_size]
            if isinstance(row, list):
                row = u''.join(row)
            rows.append(u'"' +
                        row.replace(u' ', u'_').replace(u'\0', u' ') +
                        u'"\n')
        return u''.join(rows)

    @staticmethod
    def show(positions, frame):
        # show frames for each lake position separately
        print(u'all positions:\n%s' % (LakeState.__printable_frame(frame),))
        for position in positions:
            x_min = LakeState.x_min(position)
            x_max = LakeState.x_max(position)
            y_min = LakeState.y_min(position)
            y_max = LakeState.y_max(position)
            frame_position = []
            x_size = LakeState.x_boundary_max() - LakeState.x_boundary_min() + 1
            for y_lake in range(y_min, y_max + 1):
                frame_position.extend(
                    frame[(x_size - 1) - x_max + x_size * y_lake:
                          (x_size - 1) - x_min + x_size * y_lake + 1]
                )
            print(u'position(%d) (frame x = [%d..%d], y = [%d..%d]):\n%s' % (
                position,
                x_min, x_max, y_min, y_max,
                LakeState.__printable_frame(frame_position,
                                            x_size=(x_max - x_min + 1)),
            ))
            LakeState.frames[position].append(
                u''.join(frame_position).encode('utf-8')
            )

    @staticmethod
    def tick(api):
        # display merged frames of the lake for each position
        now = default_timer()
        positions = []
        for position, frames in LakeState.frames.items():
            if frames != []:
                positions.append(position)
                frames_binary = b''.join([
                    struct.pack(b'<IBBB', len(frame) + 3,
                                0, 0, 2 ** LakeState.position) + frame
                    for frame in frames
                ])
                api.send_async(
                    LakeState.prefix(position) + 'display/merge',
                    frames_binary,
                    timeout=10000,
                )
                del LakeState.frames[position][:]
        if positions != []:
            print('sent frames for positions %s' % str(positions))
        elapsed = default_timer() - now
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

class FishState(object):
    move_rate_min = 500 # every 500 milliseconds
    move_rate_max = 1500 # every 1500 milliseconds
    move_y_chance = 0.10 # % of the time
    move_x_flip_chance = 0.60 # % of the time
    timeout_death = 2000 # milliseconds

    @staticmethod
    def fish(position_hatched, type_id, look_x_min):
        # ascii art inspired by https://github.com/lericson/fish
        fish_format = {
            0: [u"<°(%d<", u">%d)°>"], # bass
            1: [u"<·}}%d→<", u">←%d{{·>"], # salmon
            2: [u"<θ]]]]%d→<", u">←%d[[[[θ>"], # carp
        }[type_id][look_x_min]
        return fish_format % position_hatched

    def __init__(self, data_json=None):
        if data_json is not None:
            # an older fish
            data_json = json.loads(data_json)
        else:
            # a fish is born
            position = LakeState.position
            type_id = random.randint(0, 2)
            look_x_min = random.randint(0, 1) # look right?
            view = FishState.fish(position, type_id, look_x_min)
            view_x_size = len(view)
            if LakeState.x_boundary_min() == LakeState.x_min():
                x_lake = random.randint(LakeState.x_min() + view_x_size,
                                        LakeState.x_max())
            elif LakeState.x_boundary_max() == LakeState.x_max():
                x_lake = random.randint(LakeState.x_min(),
                                        LakeState.x_max() - view_x_size)
            else:
                # only would happen with more than 4 nodes
                x_lake = random.randint(LakeState.x_min(),
                                        LakeState.x_max())
            y_lake = random.randint(LakeState.y_min(),
                                    LakeState.y_max())
            data_json = {
                'fish': {
                    'position_hatched': position,
                    'type_id': type_id,
                    'look_x_min': look_x_min,
                    'view': view,
                    'view_x_size': view_x_size,
                    'view_x_center': int(round(view_x_size * 0.5)),
                    'x': x_lake,
                    'y': y_lake,
                    'move_rate': random.randint(FishState.move_rate_min,
                                                FishState.move_rate_max),
                    'move_start': default_timer(),
                    'move_y_min': random.randint(0, 1),
                    'move_count': 0,
                },
            }
        self.__data = data_json['fish']

    def __str__(self):
        return json.dumps({'fish': self.__data})

    def tick(self, timeout):
        # move and render a fish in a lake
        if timeout <= FishState.timeout_death:
            self.__render_dead()
            return None
        now = default_timer()
        if self.__data['move_start'] is None:
            self.__data['move_count'] = 0
            self.__data['move_start'] = now
            return LakeState.position
        elapsed = int((now - self.__data['move_start']) * 1000)
        if elapsed < 0:
            self.__data['move_count'] = 0
            self.__data['move_start'] = now
            return LakeState.position
        move_count = self.__data['move_count']
        count = (elapsed // self.__data['move_rate']) - move_count
        if count <= 0:
            time.sleep(0.1)
            return LakeState.position
        for _ in range(count):
            move_count += 1
            position = self.__render_move()
            if position != LakeState.position:
                break
        self.__data['move_count'] = move_count
        if position is None:
            self.__render_dead()
            return None
        return position

    def __render_dead(self):
        # pylint: disable=too-many-locals

        # render the fish disappearing
        #view = self.__data['view']
        view_x_size = self.__data['view_x_size']
        x_lake_old = self.__data['x']
        y_lake_old = self.__data['y']
        x_min = LakeState.x_boundary_min()
        x_max = LakeState.x_boundary_max()
        y_min = LakeState.y_boundary_min()
        y_max = LakeState.y_boundary_max()

        print('dead fish (%d, %d)' % (x_lake_old, y_lake_old))
        positions = set()
        x_size = x_max - x_min + 1
        y_size = y_max - y_min + 1
        frame = [u'\0'] * (x_size * y_size)
        for i in range(view_x_size):
            x_array = (x_lake_old - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y_lake_old] = u' '
                (position,
                 _, _) = LakeState.xy_local(x_lake_old - i, y_lake_old)
                positions.add(position)
        LakeState.show(positions, frame)

    def __render_move(self):
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-branches
        # pylint: disable=too-many-statements

        # move fish
        position_hatched = self.__data['position_hatched']
        type_id = self.__data['type_id']
        look_x_min = self.__data['look_x_min']
        view = self.__data['view']
        view_x_center = self.__data['view_x_center']
        view_x_size = self.__data['view_x_size']
        x_lake = self.__data['x']
        y_lake = self.__data['y']
        move_y_min = self.__data['move_y_min']
        x_lake_old = x_lake
        y_lake_old = y_lake
        if look_x_min:
            x_lake -= 1
        else:
            x_lake += 1
        if random.random() < FishState.move_y_chance:
            if move_y_min:
                y_lake -= 1
            else:
                y_lake += 1
        x_min = LakeState.x_boundary_min()
        x_max = LakeState.x_boundary_max()
        if look_x_min == 1 and x_lake < x_min:
            if random.random() < FishState.move_x_flip_chance:
                x_lake += 1
                look_x_min = 1 - look_x_min
                view = FishState.fish(position_hatched, type_id, look_x_min)
        elif look_x_min == 0 and x_lake - (view_x_size - 1) > x_max:
            if random.random() < FishState.move_x_flip_chance:
                x_lake -= 1
                look_x_min = 1 - look_x_min
                view = FishState.fish(position_hatched, type_id, look_x_min)
        y_min = LakeState.y_boundary_min()
        y_max = LakeState.y_boundary_max()
        if y_lake < y_min:
            y_lake += 1
            move_y_min = 1 - move_y_min
        elif y_lake > y_max:
            y_lake -= 1
            move_y_min = 1 - move_y_min
        self.__data['look_x_min'] = look_x_min
        self.__data['move_y_min'] = move_y_min
        self.__data['view'] = view
        self.__data['x'] = x_lake
        self.__data['y'] = y_lake

        print('moved fish (%d, %d) -> (%d, %d)' % (
            x_lake_old, y_lake_old, x_lake, y_lake,
        ))
        # render
        positions = set()
        x_size = x_max - x_min + 1
        y_size = y_max - y_min + 1
        frame = [u'\0'] * (x_size * y_size)
        for i in range(view_x_size):
            x_array = (x_lake_old - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y_lake_old] = u' '
                (position,
                 _, _) = LakeState.xy_local(x_lake_old - i, y_lake_old)
                positions.add(position)
        for i, character in enumerate(view):
            x_array = (x_lake - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y_lake] = character
                (position, _, _) = LakeState.xy_local(x_lake - i, y_lake)
                positions.add(position)
        LakeState.show(positions, frame)

        # return updated position to determine the fish's next destination
        if x_lake >= x_min and x_lake - (view_x_size - 1) <= x_max:
            (position,
             _, _) = LakeState.xy_local(x_lake - view_x_center, y_lake)
            if position is None:
                position = LakeState.position
            elif position != LakeState.position:
                self.__data['move_start'] = None # remote node time is different
            return position
        else:
            return None

class HatcheryState(object):
    # pylint: disable=too-few-public-methods

    hatch_rate = 45 # seconds (frequency of fish births)
    hatch_lifespan_min = 120 # seconds (minimum timeout)
    hatch_lifespan_max = 240 # seconds (maximum timeout)

    def __init__(self, data_json=None):
        if data_json is not None:
            # older hatchery data
            data_json = json.loads(data_json)
        else:
            # a hatchery is started
            data_json = {
                'hatchery': {
                    'hatch_start': default_timer(),
                    'hatch_count': 0,
                },
            }
        self.__data = data_json['hatchery']

    def __str__(self):
        return json.dumps({'hatchery': self.__data})

    def tick(self, api):
        # hatch new fish (1 fish is 1 CloudI service request)
        now = default_timer()
        hatch_elapsed = int(now - self.__data['hatch_start'])
        if hatch_elapsed < 0:
            self.__data['hatch_count'] = 0
            self.__data['hatch_start'] = now
            count = 0
        else:
            hatch_count = self.__data['hatch_count']
            count = (hatch_elapsed // HatcheryState.hatch_rate) - hatch_count
            if count > 0:
                self.__data['hatch_count'] = hatch_count + count
            else:
                count = 0
        for _ in range(count):
            api.send_async(
                api.prefix() + 'lake',
                str(FishState()).encode('utf-8'),
                timeout=HatcheryState.__fish_timeout(),
            )
        elapsed = default_timer() - now
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

    @staticmethod
    def __fish_timeout():
        return random.randint(HatcheryState.hatch_lifespan_min,
                              HatcheryState.hatch_lifespan_max) * 1000

class Task(threading.Thread):
    def __init__(self, i, api):
        threading.Thread.__init__(self)
        self.__thread_index = i
        self.__api = api

    def run(self):
        # pylint: disable=bare-except
        try:
            LakeState.set_position(self.__api.prefix())
            if self.__thread_index == 0:
                self.__api.send_async(
                    self.__api.prefix() + 'display',
                    b'\xff\0\0' +
                    b'                ' +
                    b'                '
                )
            if self.__thread_index == 1 or self.__thread_index == 2:
                self.__api.subscribe('view', self.__view)
            elif self.__thread_index == 3 or self.__thread_index == 4:
                self.__api.subscribe('hatchery', self.__hatchery)
            else:
                self.__api.subscribe('lake', self.__lake)
            if self.__thread_index == 0:
                self.__api.send_async(
                    self.__api.prefix() + 'view', b'',
                )
                self.__api.send_async(
                    self.__api.prefix() + 'hatchery',
                    str(HatcheryState()).encode('utf-8'),
                )

            result = self.__api.poll()
            assert result is False
        except TerminateException:
            pass
        except:
            traceback.print_exc(file=sys.stderr)
        print('terminate fish')

    def __hatchery(self, _command, _name, _pattern, _request_info, request,
                   _timeout, _priority, _trans_id, _pid):
        # pylint: disable=too-many-arguments
        state = HatcheryState(request.decode('utf-8'))
        state.tick(self.__api)
        self.__api.send_async(
            self.__api.prefix() + 'hatchery',
            str(state).encode('utf-8'),
        )

    def __view(self, _command, _name, _pattern, _request_info, _request,
               _timeout, _priority, _trans_id, _pid):
        # pylint: disable=too-many-arguments
        LakeState.tick(self.__api)
        self.__api.send_async(
            self.__api.prefix() + 'view', b'',
        )

    def __lake(self, command, _name, _pattern, request_info, request,
               timeout, priority, trans_id, pid):
        # pylint: disable=too-many-arguments
        state = FishState(request.decode('utf-8'))
        position = state.tick(timeout)
        if position is None:
            return
        self.__api.forward_(
            command, LakeState.prefix(position) + 'lake', request_info,
            str(state).encode('utf-8'), timeout, priority, trans_id, pid,
        )

if __name__ == '__main__':
    thread_count = API.thread_count()
    assert thread_count >= 1

    threads = [Task(i, API(i)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
