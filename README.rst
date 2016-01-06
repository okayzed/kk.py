==================
Kitchen Sink Pager
==================

The Kitchen Sink Pager is a pager that does more.

it's the last stop in your command pipe and rightfully so.


Installation
============

pip install KitchenSink

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


Screenshots
-------------------


KitchenSink syntax highlighting

.. image:: https://raw.github.com/okayzed/kk.py/master/images/kk.png


KitchenSink syntax highlighting vs. the traditional git diff highlighting

.. image:: https://raw.github.com/okayzed/kk.py/master/images/kk_vs_less.png

Changing Syntax Coloring
------------------------

if the syntax coloring style isn't your style or isn't showing up well, you can
use any of pygments other available styles by setting KK_STYLE environment variable.

    # listing the styles

    python -c "import pygments.styles; print pygments.styles.STYLE_MAP.keys()"

    # changing the style to vim. put this in .bashrc if you always want it

    export KK_STYLE=vim


Why another pager?
------------------

why not? operating on pipe output is one of the slower parts of my workflow.
this is an attempt to make it more bearable.
