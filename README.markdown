Odroid-C1 Fish for [CloudI](http://cloudi.org)
==============================================

Use [`odroid_display`](https://github.com/okeuday/odroid_display/) to
display CloudI service requests as UTF8-art fish on a 16x2 (blue) LCD display.
This is mainly for demonstration purposes and was inspired by
[https://github.com/lericson/fish](https://github.com/lericson/fish)
(which is also in Python).

4 Odroid-C1 CloudI nodes are used to demonstrate both local and remote
service request communication, with the "lake" configuration
(Odroid-C1 node positions with 16x2 LCD displays) as:

    
    (node 2)        (node 0)
    
    (node 3)        (node 1)
    

The separate CloudI configuration files for each node are provided
along with the fish.py Python CloudI service.

Details
-------

Each UTF8 fish contains the node integer that created the fish, so the
node integer follows the fish in the LCD display as it swims to other nodes.
The types of fish are shown below (for node 0):

    >0)°>       bass
    >←0{{·>     salmon
    >←0[[[[θ>   carp

The fish are JSON data sent within CloudI service requests, with a timeout
that determines the lifetime of the fish.  Separate service requests
manage the hatchery and view updates with regular "tick" intervals.

The 16x2 LCD display also provides 7 status LEDs below the LCD.  These LEDs
are toggled whenever a view update comes from a specific node
(so a view update from node X toggles LED #X on the destination node Y).
Once a fish's position crosses a node boundary, the fish's service request
passes to the remote node (as shown at the end of `FishState.__render_move`).
The internal time kept within the fish's JSON data is reset before the send
to a remote node, since it is assumed that there is no clock synchronization
in-place.

Running CloudI with the provided configurations on the 4 Odroid-C1s
(not including a Netgear GS108 Gigabit Switch) consumes a total of ~14 watts.

Example
-------

![](https://raw.githubusercontent.com/okeuday/odroid_fish/master/fishbowl.gif)

Author
------

Michael Truog (mjtruog [at] gmail (dot) com)

License
-------

BSD

