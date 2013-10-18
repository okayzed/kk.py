==================
Kitchen Sink Pager
==================

The Kitchen Sink Pager is a pager that does more.

it's the last stop in your command pipe and rightfully so.

Examples
=========
::

    # use it for paging. sometimes, it can even figure out
    # the filetype and add syntax highlighting. (press 's')
    cat some_file.py | kk

    # Use it as a quick file jumper for grep results.
    # Press 'f' to quickly view a file in the current buffer
    grep * -Rn my_string | kk

    # Use it as a git log viewer.
    # press 'o' to find all git [o]bjects
    # press 'f' to find [f]iles.
    git log | kk

    # it does git diff highlighting, too
    # press 's' to toggle highlighting
    git log --color -n1 -p | kk

    # if there are numbers in the buffer,
    # the kitchen sink math them with 'm'
    cat lots_of_numbers.txt | kk

Why another pager?
------------------

why not? operating on pipe output is one of the slower parts of my workflow.
this is an attempt to make it more bearable.
