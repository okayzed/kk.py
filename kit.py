#!/usr/bin/env python
# -*- coding: latin-1 -*-

# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# things the kitchen sink could potentially do:

# add syntax highlighting to any output
# locate (and open) files in the output
# locate (and open) urls in the output
# compare two different outputs (do ad-hoc diffs)
# open the output in an editor
# build a command (from portions of the output?)
# do maths with the output
#  calculate sums
#  pivot tables



import curses
import itertools
import os
import sys
import time
import urlparse
import urwid

import pygments
import pygments.formatters
from urwidpygments import UrwidFormatter
from pygments.lexers import guess_lexer


debugfile = open(__name__ + ".debug", "w")
def debug(msg):
  print >> debugfile, msg

def read_lines(stdscr):
  maxx = 0
  numlines = 0
  lines = []
  for line in sys.stdin:
    maxx = max(maxx, len(line))
    numlines += 1
    lines.append(line)

  maxy = numlines

  joined = ''.join(lines)

  # this is the second pass, and where the actual parsing of tokens should
  # probably happen. In addition, we should look at the tokens in each line and
  # maybe highlight specific ones? #www.yahoo.com


  # http://redd.it
  all_tokens = []
  for index, line in enumerate(lines):
    col = 0

    while line[col] == " ":
      col += 1

    tokens = line.split()
    for token in tokens:
      all_tokens.append({
        "text" : token.strip(),
        "line" : index,
        "col" : col
      })

      col += len(token) + 1

  return {
    "maxx": maxx,
    "maxy": maxy,
    "lines": lines,
    "joined" : joined,
    "tokens" : all_tokens
  }


"http://google.com"

"http://yahoo.com"





# http://stackoverflow.com/questions/2576956/getting-data-from-external-program
def _get_content(editor, initial=""):
    from subprocess import call
    from tempfile import NamedTemporaryFile

    # Create the initial temporary file.
    with NamedTemporaryFile(delete=False) as tf:
        tfName = tf.name
        debug("opening file in editor:" + str(tfName))
        tf.write(initial)

    # Fire up the editor.
    if call([editor, tfName]) != 0:
        return None # Editor died or was killed.

    # Get the modified content.


    try:
      with open(tfName).readlines() as result:
          os.remove(tfName)
          return result
    except:
      pass


def do_syntax_coloring(ret, walker=None):
  lexer = guess_lexer(ret['joined'])

  formatter = UrwidFormatter()
  lines = ret['lines']
  output = ret['joined']
  # special case for git diffs
  if ret['joined'].find("diff --git") >= 0:
    walker[:] = [ ]
    wlines = []
    lexer = None
    fname = None
    for line in lines:
      if line.startswith("diff --git"):

        # previous output
        if fname:
          output = "".join(wlines)

          try:
            lexer = pygments.lexers.guess_lexer_for_filename(fname, output)
          except:
            lexer = guess_lexer(output)
          tokens = lexer.get_tokens(output)
          formatted_tokens = formatter.formatgenerator(tokens)
          walker.append(urwid.Text(list(formatted_tokens)))

        # next output
        fname = line.split().pop()
        wlines = [ ]

      wlines.append(line)

    if wlines:
      lexer = pygments.lexers.guess_lexer_for_filename(fname, "\n".join(wlines))
      tokens = lexer.get_tokens(output)
      formatted_tokens = formatter.formatgenerator(tokens)
      walker.append(urwid.Text(list(formatted_tokens)))

    pass
  else:
    # otherwise, just try and highlight the whole text at once
    tokens = lexer.get_tokens(output)
    formatted_tokens = formatter.formatgenerator(tokens)

    walker[:] = [ urwid.Text(list(formatted_tokens)) ]


def do_get_urls(ret, scr=None):
  tokens = ret['tokens']

  def func():
    urls = []
    import re
    for token in tokens:
      match = re.search("^\W*(https?://[\w\.]*|www.[\w\.]*)", token['text'])
      if match:
        urls.append(match.group(1))

    print '\n'.join(urls)

  after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_interactive_sed(ret, scr=None):
  pass

after_urwid = []
def do_quit(ret, scr):
  raise urwid.ExitMainLoop()

def do_edit_text(ret, widget):
  _get_content(os.environ["EDITOR"], ret["joined"])
  raise urwid.ExitMainLoop()

palette = [
  ('banner', 'black', 'light gray'),
  ('streak', 'black', 'dark red'),
  ('bg', 'black', 'dark blue'),
]

def main(stdscr):
  ret = read_lines(stdscr)
  widget = None
  walker = None


  # We're done with stdin,
  # now we want to read input from current terminal
  with open("/dev/tty") as f:
    os.dup2(f.fileno(), 0)

  def handle_input(key):
    if type(key) == str:
      key = key.lower()

    y, x = stdscr.getmaxyx()

    curses_hooks = {
      "q" : do_quit,
      "s" : do_interactive_sed,
      "c" : do_syntax_coloring,
      "u" : do_get_urls,
      "e" : do_edit_text
    }

    if key in curses_hooks:
      val = curses_hooks[key](ret, walker)
      if val:
        return val

  wlist = []
  for line in ret["lines"]:
    col = 0
    stripped = line.lstrip()
    col = len(line) - len(stripped)

    wlist.append(urwid.Text(line.rstrip()))

  walker = urwid.SimpleListWalker(wlist)
  widget = urwid.ListBox(walker)

  loop = urwid.MainLoop(widget, palette, unhandled_input=handle_input)
  loop.run()

if __name__ == "__main__":
  curses.wrapper(main)
  for after in after_urwid:
    if hasattr(after, '__call__'):
      try:
        after()
      except Exception, e:
        raise e
