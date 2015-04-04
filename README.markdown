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

Author
------

Michael Truog (mjtruog [at] gmail (dot) com)

License
-------

BSD

