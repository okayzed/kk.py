==================
Kitchen Sink Pager
==================

The Kitchen Sink Pager is a pager that does more. It's the last stop in your
command pipe and rightfully so.

Examples
=========
::

    # Use it as a git log viewer. Press 'o' to find all git [o]bjects in the current buffer.
    # Press 'f' to find files.
    git log | kk
    # Use it as a quick file jumper for grep results. Press 'f' to quickly view
    # a file in the current # buffer
    grep * -Rn my_string | kk
    # just use it for paging. sometimes, it can even figure out
    # the filetype and add syntax highlighting. (press 's')
    cat some_file.py | kk
    # it does git diff highlighting, too (press 's' to toggle highlighting)
    git log --color -n1 -p | kk



Why another pager?
------------------

why not? operating on pipe output is one of the more painful parts of my workflow.
this is an attempt to make it more bearable.
