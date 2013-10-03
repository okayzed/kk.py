#!/usr/bin/env python
# -*- coding: latin-1 -*-

# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# things the kitchen sink could potentially do:

# o locate (and open) files in the output
# o compare two different outputs (do ad-hoc diffs)
# o build a command (from portions of the output?)
# o yank the output into a 'buffer'
# o open urls from the output
# x add syntax highlighting to any output
# x add syntax highlighting to git diffs
# x open the output in an editor
# x locate urls in the output

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

# {{{ util
def add_vim_movement():
  updatedMappings = {
    'k':        'cursor up',
    'j':      'cursor down',
    'h':      'cursor left',
    'l':     'cursor right',
    'ctrl u':   'cursor page up',
    'ctrl d': 'cursor page down'
  }

  for key in updatedMappings:
    urwid.command_map[key] = updatedMappings[key]


debugfile = open(__name__ + ".debug", "w")
def debug(*args):
  print >> debugfile, " ".join([str(i) for i in args])

# }}}

# {{{ read input
def read_lines(lines=None):
  maxx = 0
  numlines = 0
  lines = []
  content = False

  for line in (lines or sys.stdin):
    maxx = max(maxx, len(line))
    numlines += 1
    lines.append(line)
    if not content and line.strip() != "":
      content = True

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
    "tokens" : all_tokens,
    "has_content" : content
  }


"http://google.com"

"http://yahoo.com"

# }}}

# {{{ http://stackoverflow.com/questions/2576956/getting-data-from-external-program
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
# }}}

# {{{ Overlay Stack
class OverlayStack(urwid.WidgetPlaceholder):
  def __init__(self, *args, **kwargs):
    super(OverlayStack, self).__init__(*args, **kwargs)
    self.overlay_opened = False

  def open_overlay(self, widget, modal_keys=None, **options):
    global _key_hooks
    if not modal_keys:
      modal_keys = {}

    modal_keys.update({ "q" : CURSES_HOOKS['q'], "esc" : CURSES_HOOKS['esc'] })
    # we should install these modal keys
    _key_hooks = modal_keys

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
    global _key_hooks
    self.original_widget = self.overlay_parent
    self.overlay_opened = False
    _key_hooks = CURSES_HOOKS

# }}}

# {{{ character handlers
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

    if len(wlines):
      output = "".join(wlines)
      lexer = pygments.lexers.guess_lexer_for_filename(fname, output)
      tokens = lexer.get_tokens(output)
      formatted_tokens = formatter.formatgenerator(tokens)
      walker.append(urwid.Text(list(formatted_tokens)))
  else:
    # otherwise, just try and highlight the whole text at once
    tokens = lexer.get_tokens(output)
    formatted_tokens = formatter.formatgenerator(tokens)

    walker[:] = [ urwid.Text(list(formatted_tokens)) ]

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


def do_pipe(ret, scr):
  def func():
    print ret['joined']

  after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_interactive_sed(ret, scr=None):
  pass

after_urwid = []
def do_close_overlay_or_quit(ret, widget):
  if  widget.overlay_opened:
    debug("CLOSING OVERLAY")
    widget.close_overlay()
  else:
    debug("QUITTING")
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

def do_yank_text(ret, widget):
  success = urwid.Text("Success")
  listbox = urwid.ListBox([success])

  widget.open_overlay(urwid.LineBox(listbox), height=3)

def do_diff_text(ret, widget):
  pass

def do_scroll_top(ret, widget):
  widget.original_widget.set_focus(0)

def do_scroll_bottom(ret, widget):
  debug("SCROLLING TO THE BOTTOM")
  debug(widget.original_widget.body)
  widget.original_widget.set_focus(len(widget.original_widget.body))

def do_general(ret, widget):
  debug("DOING GENERAL")
  setup_general_hooks()

def do_open_help(ret, widget):
  listitems = []

  helps = []
  shortcuts = []
  for item in _key_hooks:
    msg = _key_hooks[item].get('help')
    if msg:
      shortcut = urwid.Text(('banner', item))
      shortcut.align = "right"
      help_msg = urwid.Text(msg + "  ")
      help_msg.align = "right"

      columns = urwid.Columns([ ("fixed", 3, shortcut), ("weight", 90, help_msg)])
      listitems.append(columns)

  listbox = urwid.ListBox(listitems)
  widget.open_overlay(urwid.LineBox(listbox),
    width=("relative", 80), height=("relative", 80))

CURSES_HOOKS = {
  "q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Quit kit / Close current overlay"
  },
  "s" : {
    "fn" : do_interactive_sed,
    "help" : "Open interactive sed editor"
  },
  "p" : {
    "fn" : do_pipe,
    "help" : "Pipe kits window to another command"
  },
  "c" : {
    "fn" : do_syntax_coloring,
    "help" : "turn on syntax highlights"
  },
  "u" : {
    "fn" : do_get_urls,
    "help" : "dump the URLs from the current buffer"
  },
  "e" : {
    "fn" : do_edit_text,
    "help" : "open the current text in $EDITOR"
  },
  "g" : {
    "fn" : do_general,
    "help" : "enter general mode"
  },
  "G" : {
    "fn" : do_scroll_bottom,
    "help" : ""
  },
  "y" : {
    "fn" : do_yank_text,
    "help" : "save the current kit output for later use"
  },
  "d" : {
    "fn" : do_diff_text,
    "help" : "compare the current kit session against a previous session"
  },
  "?" : {
    "fn" : do_open_help,
    "help" : "show this screen"
  },
  "esc" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Close kit / Close current overlay"
  },
}

GENERAL_HOOKS = {
  "?" : {
    "fn" : do_open_help,
    "help" : "Show this screen"
  },
  "q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Close this overlay"
  },
  "g" : {
    "fn" : do_scroll_top,
    "help" : "Scroll to top of content"
  }
}

debug("SETTING UP GENERAL HOOKS")
for hook in GENERAL_HOOKS:
  def build_replacement():
    obj = GENERAL_HOOKS[hook]

    def replacement(*args, **kwargs):
      global _key_hooks
      debug("CALLING REPLACEMENT FUNCTION", obj)
      obj['oldfn'](*args, **kwargs)
      _key_hooks = CURSES_HOOKS

    obj['oldfn'] = obj['fn']
    obj['fn'] = replacement

  build_replacement()


def setup_general_hooks():
  global _key_hooks

  debug("USING GENERAL HOOKS")
  _key_hooks = GENERAL_HOOKS


# }}}

# {{{ display input
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

# }}}


# {{{
_key_hooks = CURSES_HOOKS
def main(stdscr):
  ret = read_lines(stdscr)
  # We're done with stdin,
  # now we want to read input from current terminal
  with open("/dev/tty") as f:
    os.dup2(f.fileno(), 0)

  def handle_input(keys, raw):
    global _key_hooks
    unhandled = []
    debug("HANDLING INPUT", keys)

    was_general = False
    # always switch back
    if _key_hooks == GENERAL_HOOKS:
      was_general = True

    for key in keys:
      if not unhandle_input(key):
        unhandled.append(key)

    if was_general:
      _key_hooks = CURSES_HOOKS
      return []

    return unhandled

  def unhandle_input(key):
    debug("UNHANDLING INPUT", key)
    if key in _key_hooks.keys():
      debug("KEY ", key, "PRESSED")
      _key_hooks[key]['fn'](ret, widget)
      return True

  add_vim_movement()
  widget = OverlayStack(urwid.Text(""))
  display_lines(ret["lines"], widget)

  loop = urwid.MainLoop(widget, palette, unhandled_input=unhandle_input, input_filter=handle_input)
  if ret['has_content']:
    loop.run()


if __name__ == "__main__":
  curses.wrapper(main)
  for after in after_urwid:
    if hasattr(after, '__call__'):
      try:
        after()
      except Exception, e:
        raise e
# }}}
