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




# Things that will be useful in this UI
#   modal overlay stack
#



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

def read_lines(lines=None):
  maxx = 0
  numlines = 0
  lines = []

  for line in (lines or sys.stdin):
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

    tfName = None
    # Create the initial temporary file.
    with NamedTemporaryFile(delete=False) as tf:
        tfName = tf.name
        debug("opening file in editor:" + str(tfName))
        tf.write(initial)

    # Fire up the editor.
    code = call([editor, tfName])
    if code != 0:
        return None # Editor died or was killed.

    # Get the modified content.
    with open(tfName, "r") as f:
        result = f.readlines()
        os.remove(tfName)
        return result


syntax_colored = False
previous_widget = None
def do_syntax_coloring(ret, widget):
  global previous_widget, syntax_colored
  walker = urwid.SimpleListWalker([])

  if previous_widget:
    original_text = widget.original_widget
    widget.original_widget = previous_widget
    previous_widget = original_text

    syntax_colored = not syntax_colored
    return


  # one time setup
  previous_widget = widget.original_widget
  listbox = urwid.ListBox(walker)
  widget.original_widget = listbox
  syntax_colored = True

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

class MainWindow(urwid.WidgetPlaceholder):
  def __init__(self, *args, **kwargs):
    super(MainWindow, self).__init__(*args, **kwargs)
    self.overlay_opened = False

  def open_overlay(self, widget, **options):
    if not self.overlay_opened:
      defaults = {
        "align" : "center",
        "width" : ("relative", 50),
        "valign" : "middle",
        "height" : ("relative", 50)
      }
      defaults.update(options)

      overlay = urwid.Overlay(
        widget,
        self.original_widget,
        **defaults
      )

      self.overlay_parent = self.original_widget
      self.overlay = overlay

      self.original_widget = self.overlay

    self.overlay_opened = True

  def close_overlay(self, ret=None, widget=None):
    self.original_widget = self.overlay_parent
    self.overlay_opened = False

def do_get_urls(ret, widget=None):
  tokens = ret['tokens']

  urls = []
  import re
  for token in tokens:
    match = re.search("^\W*(https?://[\w\.]*|www.[\w\.]*)", token['text'])
    if match:
      urls.append(match.group(1))


  if not len(urls):
    urls.append("No URLS found in document")

  walker = urwid.SimpleListWalker([urwid.Text(url) for url in urls])
  listbox = urwid.ListBox(walker)
  url_window = urwid.LineBox(listbox)
  widget.open_overlay(url_window)


def do_print(ret, scr):
  def func():
    print ret['joined']

  after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_interactive_sed(ret, scr=None):
  pass

after_urwid = []

def do_close_overlay_or_quit(ret, widget):
  if  widget.overlay_opened:
    widget.close_overlay()
  else:
    raise urwid.ExitMainLoop()

def do_quit(ret, scr):
  raise urwid.ExitMainLoop()

def do_edit_text(ret, widget):
  global previous_widget, syntax_colored

  lines = _get_content(os.environ["EDITOR"], ret["joined"])
  previous_widget = None
  syntax_colored = False
  display_lines(lines, widget)
  ret['lines'] = lines
  ret['joined'] = ''.join(lines)

palette = [
  ('banner', 'black', 'light gray'),
  ('streak', 'black', 'dark red'),
  ('bg', 'black', 'dark blue'),
]

def display_lines(lines, widget):
  wlist = []
  for line in lines:
    col = 0
    stripped = line.lstrip()
    col = len(line) - len(stripped)

    wlist.append(urwid.Text(line.rstrip()))

  walker = urwid.SimpleListWalker(wlist)
  text = urwid.ListBox(walker)
  widget.original_widget = text

def main(stdscr):
  ret = read_lines(stdscr)

  # We're done with stdin,
  # now we want to read input from current terminal
  with open("/dev/tty") as f:
    os.dup2(f.fileno(), 0)

  def handle_input(key):
    if type(key) == str:
      key = key.lower()

    y, x = stdscr.getmaxyx()

    curses_hooks = {
      "q" : do_close_overlay_or_quit,
      "s" : do_interactive_sed,
      "p" : do_print,
      "c" : do_syntax_coloring,
      "u" : do_get_urls,
      "e" : do_edit_text,
      "esc" : widget.close_overlay
    }

    if key in curses_hooks:
      val = curses_hooks[key](ret, widget)
      if val:
        return val


  widget = MainWindow(urwid.Text(""))
  display_lines(ret["lines"], widget)

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
