#!/usr/bin/env python
#-*-Mode:python;coding:utf-8;tab-width:4;c-basic-offset:4;indent-tabs-mode:()-*-
# ex: set ft=python fenc=utf-8 sts=4 ts=4 sw=4 et:
#
# MIT License
#
# Copyright (c) 2015-2017 Michael Truog <mjtruog at gmail dot com>
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

import sys
sys.path.append('/usr/local/lib/cloudi-1.7.0/api/python/')

import threading, types, traceback
from cloudi import API, terminate_exception
from timeit import default_timer
import json, struct, time, random

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
        return ('/odroid/fish/%d/' % position)

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
    def xy_local(x, y):
        if x <= (LakeState.columns * 1 - 1):
            if y <= (LakeState.rows * 1 - 1):
                return (0, x, y)
            elif y <= (LakeState.rows * 2 - 1):
                return (1, x, y - LakeState.rows * 1)
            else:
                return (None, None, None)
        elif x <= (LakeState.columns * 2 - 1):
            if y <= (LakeState.rows * 1 - 1):
                return (2, x - LakeState.columns * 1, y)
            elif y <= (LakeState.rows * 2 - 1):
                return (3, x - LakeState.columns * 1, y - LakeState.rows * 1)
            else:
                return (None, None, None)
        else:
            return (None, None, None)

    @staticmethod
    def __printable_frame(frame, x_size=None):
        if x_size is None:
            x_size = LakeState.x_boundary_max() - LakeState.x_boundary_min() + 1
        rows = []
        for x in range(0, len(frame), x_size):
            row = frame[x:x + x_size]
            if type(row) == list:
                row = u''.join(row)
            rows.append(u'"' +
                        row.replace(u' ',u'_').replace(u'\0', u' ') +
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
            for y in range(y_min, y_max + 1):
                frame_position.extend(
                    frame[(x_size - 1) - x_max + x_size * y:
                          (x_size - 1) - x_min + x_size * y + 1]
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
            if len(frames) > 0:
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
        if len(positions) > 0:
            print('sent frames for positions %s' % str(positions))
        elapsed = default_timer() - now
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

class FishState(object):
    move_rate_min =  500 # every 500 milliseconds
    move_rate_max = 1500 # every 1500 milliseconds
    move_y_chance = 0.10 # % of the time
    move_x_flip_chance = 0.60 # % of the time
    timeout_death = 2000 # milliseconds

    @staticmethod
    def fish(position_hatched, type_id, look_x_min):
        # ascii art inspired by https://github.com/lericson/fish
        fish_format = {
            0: [u"<°(%d<",         u">%d)°>"], # bass
            1: [u"<·}}%d→<",     u">←%d{{·>"], # salmon
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
                x = random.randint(LakeState.x_min() + view_x_size,
                                   LakeState.x_max())
            elif LakeState.x_boundary_max() == LakeState.x_max():
                x = random.randint(LakeState.x_min(),
                                   LakeState.x_max() - view_x_size)
            else:
                # only would happen with more than 4 nodes
                x = random.randint(LakeState.x_min(),
                                   LakeState.x_max())
            y = random.randint(LakeState.y_min(),
                               LakeState.y_max())
            data_json = {
                'fish': {
                    'position_hatched': position,
                    'type_id': type_id,
                    'look_x_min': look_x_min,
                    'view': view,
                    'view_x_size': view_x_size,
                    'view_x_center': int(round(view_x_size * 0.5)),
                    'x': x,
                    'y': y,
                    'move_rate': random.randint(FishState.move_rate_min,
                                                FishState.move_rate_max),
                    'move_start': default_timer(),
                    'move_y_min': random.randint(0, 1),
                    'move_count': 0,
                },
            }
        self.__data = data_json['fish']

    def __str__(self):
        return json.dumps({'fish': self.__data}).encode('utf-8')

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
        count = (elapsed / self.__data['move_rate']) - move_count
        if count <= 0:
            time.sleep(0.1)
            return LakeState.position
        for i in range(count):
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
        # render the fish disappearing
        view = self.__data['view']
        view_x_size = self.__data['view_x_size']
        x_old = self.__data['x']
        y_old = self.__data['y']
        x_min = LakeState.x_boundary_min()
        x_max = LakeState.x_boundary_max()
        y_min = LakeState.y_boundary_min()
        y_max = LakeState.y_boundary_max()

        print('dead fish (%d, %d)' % (x_old, y_old))
        positions = set()
        x_size = x_max - x_min + 1
        y_size = y_max - y_min + 1
        frame = [u'\0'] * (x_size * y_size)
        for i in range(view_x_size):
            x_array = (x_old - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y_old] = u' '
                (position, tmp, tmp) = LakeState.xy_local(x_old - i, y_old)
                positions.add(position)
        LakeState.show(positions, frame)

    def __render_move(self):
        # move fish
        position_hatched = self.__data['position_hatched']
        type_id = self.__data['type_id']
        look_x_min = self.__data['look_x_min']
        view = self.__data['view']
        view_x_center = self.__data['view_x_center']
        view_x_size = self.__data['view_x_size']
        x = self.__data['x']
        y = self.__data['y']
        move_y_min = self.__data['move_y_min']
        x_old = x
        y_old = y
        if look_x_min:
            x -= 1
        else:
            x += 1
        if random.random() < FishState.move_y_chance:
            if move_y_min:
                y -= 1
            else:
                y += 1
        x_min = LakeState.x_boundary_min()
        x_max = LakeState.x_boundary_max()
        if look_x_min == 1 and x < x_min:
            if random.random() < FishState.move_x_flip_chance:
                x += 1
                look_x_min = 1 - look_x_min
                view = FishState.fish(position_hatched, type_id, look_x_min)
        elif look_x_min == 0 and x - (view_x_size - 1) > x_max:
            if random.random() < FishState.move_x_flip_chance:
                x -= 1
                look_x_min = 1 - look_x_min
                view = FishState.fish(position_hatched, type_id, look_x_min)
        y_min = LakeState.y_boundary_min()
        y_max = LakeState.y_boundary_max()
        if y < y_min:
            y += 1
            move_y_min = 1 - move_y_min
        elif y > y_max:
            y -= 1
            move_y_min = 1 - move_y_min
        self.__data['look_x_min'] = look_x_min
        self.__data['move_y_min'] = move_y_min
        self.__data['view'] = view
        self.__data['x'] = x
        self.__data['y'] = y

        print('moved fish (%d, %d) -> (%d, %d)' % (x_old, y_old, x, y))
        # render
        positions = set()
        x_size = x_max - x_min + 1
        y_size = y_max - y_min + 1
        frame = [u'\0'] * (x_size * y_size)
        for i in range(view_x_size):
            x_array = (x_old - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y_old] = u' '
                (position, tmp, tmp) = LakeState.xy_local(x_old - i, y_old)
                positions.add(position)
        for i, c in enumerate(view):
            x_array = (x - i)
            if x_array >= 0 and x_array < x_size:
                frame[(x_size - 1) - x_array + x_size * y] = c
                (position, tmp, tmp) = LakeState.xy_local(x - i, y)
                positions.add(position)
        LakeState.show(positions, frame)

        # return updated position to determine the fish's next destination
        if x >= x_min and x - (view_x_size - 1) <= x_max:
            (position, tmp, tmp) = LakeState.xy_local(x - view_x_center, y)
            if position is None:
                position = LakeState.position
            elif position != LakeState.position:
                self.__data['move_start'] = None # remote node time is different
            return position
        else:
            return None

class HatcheryState(object):
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
        return json.dumps({'hatchery': self.__data}).encode('utf-8')

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
            count = (hatch_elapsed / HatcheryState.hatch_rate) - hatch_count
            if count > 0:
                self.__data['hatch_count'] = hatch_count + count
            else:
                count = 0
        for i in range(count):
            api.send_async(
                api.prefix() + 'lake', str(FishState()),
                timeout=self.__fish_timeout(),
            )
        elapsed = default_timer() - now
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

    def __fish_timeout(self):
        return random.randint(HatcheryState.hatch_lifespan_min,
                              HatcheryState.hatch_lifespan_max) * 1000

class Task(threading.Thread):
    def __init__(self, i, api):
        threading.Thread.__init__(self)
        self.__thread_index = i
        self.__api = api

    def run(self):
        try:
            LakeState.set_position(self.__api.prefix())
            if self.__thread_index == 0:
                self.__api.send_async(
                    self.__api.prefix() + 'display',
                    b'\xff\0\0' +
                    b'                ' +
                    b'                '
                )
            if (self.__thread_index == 1 or
                self.__thread_index == 2):
                self.__api.subscribe('view', self.__view)
            elif (self.__thread_index == 3 or
                  self.__thread_index == 4):
                self.__api.subscribe('hatchery', self.__hatchery)
            else:
                self.__api.subscribe('lake', self.__lake)
            if self.__thread_index == 0:
                self.__api.send_async(
                    self.__api.prefix() + 'view', b'',
                )
                self.__api.send_async(
                    self.__api.prefix() + 'hatchery', str(HatcheryState()),
                )

            result = self.__api.poll()
            assert result == False
        except terminate_exception:
            pass
        except:
            traceback.print_exc(file=sys.stderr)
        print('terminate fish')

    def __hatchery(self, command, name, pattern, request_info, request,
                   timeout, priority, trans_id, pid):
        state = HatcheryState(request)
        state.tick(self.__api)
        self.__api.send_async(
            self.__api.prefix() + 'hatchery', str(state),
        )

    def __view(self, command, name, pattern, request_info, request,
               timeout, priority, trans_id, pid):
        LakeState.tick(self.__api)
        self.__api.send_async(
            self.__api.prefix() + 'view', '',
        )

    def __lake(self, command, name, pattern, request_info, request,
               timeout, priority, trans_id, pid):
        state = FishState(request)
        position = state.tick(timeout)
        if position is None:
            return
        self.__api.forward_(
            command, LakeState.prefix(position) + 'lake', request_info,
            str(state), timeout, priority, trans_id, pid
        )

if __name__ == '__main__':
    thread_count = API.thread_count()
    assert thread_count >= 1
    
    threads = [Task(i, API(i)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

