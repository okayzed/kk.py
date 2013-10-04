#!/usr/bin/env python
# -*- coding: latin-1 -*-

# {{{ about
# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# things the kitchen sink could potentially do:

# o compare two different outputs (do ad-hoc diffs)
# o pipe buffer into a command and re-open pager
# o yank the output into a 'buffer'
# o search + next / prev functions
# o sum a column
# o sum a row

# x locate (and open) files in the output
# x open urls from the output
# x add syntax highlighting to any output
# x add syntax highlighting to git diffs
# x open the output in an external editor
# x locate urls in the output

# }}}

# {{{ imports
import curses
import itertools
import os
import subprocess
import sys
import time
import urlparse
import urwid

import pygments
import pygments.formatters
from urwidpygments import UrwidFormatter
from pygments.lexers import guess_lexer
# }}}

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

# {{{ input
def tokenize(lines):
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
  return all_tokens

def read_lines(in_lines=None):
  maxx = 0
  numlines = 0
  content = False
  debug("LIENS", in_lines)

  if not in_lines:
    in_lines = list(sys.stdin.readlines())

  lines = []
  for line in in_lines:
    maxx = max(maxx, len(line))
    numlines += 1
    line = line.replace('[\x01-\x1F\x7F]', '')
    lines.append(line)
    if not content and line.strip() != "":
      content = True

  maxy = numlines

  joined = ''.join(lines)

  # this is the second pass, and where the actual parsing of tokens should
  # probably happen. In addition, we should look at the tokens in each line and
  # maybe highlight specific ones? #www.yahoo.com

  all_tokens = tokenize(lines)

  return {
    "maxx": maxx,
    "maxy": maxy,
    "lines": lines,
    "joined" : joined,
    "tokens" : all_tokens,
    "has_content" : content
  }


"http://google.com/the/first/one"

"http://yahoo.com/?asecond=eht"

# }}}

# {{{ external editor
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
# }}}

# {{{ overlay widget
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
def do_syntax_coloring(kv, ret, widget):
  global previous_widget, syntax_colored
  walker = urwid.SimpleListWalker([])

  if previous_widget:
    original_text = widget.original_widget
    widget.original_widget = previous_widget
    previous_widget = original_text

    debug("SYNTAX COLORING PREV WIDGET")

    syntax_colored = not syntax_colored
    return


  debug("INITIALIZING SYNTAX COLORED WIDGET")
  # one time setup
  previous_widget = widget.original_widget
  listbox = urwid.ListBox(walker)
  widget.original_widget = listbox
  syntax_colored = True

  formatter = UrwidFormatter()
  # special case for git diffs
  def add_lines_to_walker(lines, walker, fname=None):
    if len(lines):
      output = "".join(lines)
      lexer = guess_lexer(output)
      try:
        if fname:
          lexer = pygments.lexers.guess_lexer_for_filename(fname, output)
      except:
        pass

      tokens = lexer.get_tokens(output)

      # Build the syntax output up line by line, so that it can be highlighted
      # one line at a time
      formatted_tokens = list(formatter.formatgenerator(tokens))
      formatted_line = []
      for token in formatted_tokens:
        if token[1] == '\n':
          if formatted_line:
            walker.append(urwid.Text(formatted_line))
            formatted_line = []
        else:
          formatted_line.append(token)

      if formatted_line:
        walker.append(urwid.Text(list(formatted_line)))


  if ret['joined'].find("diff --git") >= 0:
    walker[:] = [ ]
    wlines = []
    lexer = None
    fname = None

    for line in ret['lines']:
      if line.startswith("diff --git"):
        output = "".join(wlines)

        add_lines_to_walker(wlines, walker, fname)

        # next output
        fname = line.split().pop()
        wlines = [ ]

      wlines.append(line)

    add_lines_to_walker(wlines, walker, fname)
  else:
    lines = ret['lines']
    add_lines_to_walker(lines, walker, None)

  # an anchor blank element for easily scrolling to bottom of this text view
  walker.append(urwid.Text(''))

def overlay_menu(widget, title, items, cb):
  def button(text, value):
    def button_pressed(but):
      debug("BUTTON PRESSED", title, text)
      cb(text)

    button = urwid.Button(text[:40], on_press=button_pressed)

    return button

  walker = urwid.SimpleListWalker([button(token, token) for token in items])
  walker.insert(0, urwid.Text(title))
  listbox = urwid.ListBox(walker)
  url_window = urwid.LineBox(listbox)
  widget.open_overlay(url_window)

def do_get_files(kv, ret, widget):
  tokens = ret['tokens']
  files = []
  for token in tokens:
    if os.path.isfile(token['text']):
      files.append(token['text'])

  if not len(files):
    files.append("No files found in document")

  def func(response):
    try:
      with open(response, "r") as f:
        contents = list(f.readlines())
        debug("READ FILE", contents)
        widget.close_overlay()
        previous_widget = None
        syntax_colored = False
        kv.ret = read_lines(contents)
        display_lines(contents, widget)
    except Exception, e:
      debug("EXCEPTION", e)

  overlay_menu(widget, "Choose a file to open", files, func)

def do_get_urls(kv, ret, widget=None):
  tokens = ret['tokens']

  urls = []
  import re
  for token in tokens:
    match = re.search("^\W*(https?://[\w\./]*|www.[\w\./\?&\.]*)", token['text'])
    if match:
      urls.append(match.group(1))


  if not len(urls):
    urls.append("No URLS found in document")

  def func(response):
    if not response.startswith('http'):
      response = "http://%s" % response
    subprocess.Popen(["/usr/bin/xdg-open", response])
    widget.close_overlay()

  overlay_menu(widget, "Choose a URL to open", urls, func)

def do_print(kv, ret, scr):
  def func():
    print ret['joined']

  kv.after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_interactive_sed(kv, ret, scr=None):
  pass

def do_close_overlay_or_quit(kv, ret, widget):
  if  widget.overlay_opened:
    debug("CLOSING OVERLAY")
    widget.close_overlay()
  else:
    debug("QUITTING")
    raise urwid.ExitMainLoop()

def do_quit(kv, ret, scr):
  raise urwid.ExitMainLoop()

def do_edit_text(kv, ret, widget):
  global previous_widget, syntax_colored

  lines = _get_content(os.environ["EDITOR"], ret["joined"])
  previous_widget = None
  syntax_colored = False
  display_lines(lines, widget)
  ret['lines'] = lines
  ret['joined'] = ''.join(lines)
  ret['tokens'] = tokenize(lines)

def do_yank_text(kv, ret, widget):
  success = urwid.Text("Success")
  listbox = urwid.ListBox([success])

  widget.open_overlay(urwid.LineBox(listbox), height=3)

def do_diff_text(kv, ret, widget):
  pass

def do_next_search(kv, ret, widget):
  kv.find_and_focus()

def do_prev_search(kv, ret, widget):
  kv.display_status_msg("Reverse search is yet unimplemented")

def do_scroll_top(kv, ret, widget):
  widget.original_widget.set_focus_valign('top')
  widget.original_widget.set_focus(0)

def do_scroll_bottom(kv, ret, widget):
  widget.original_widget.set_focus_valign("bottom")
  debug(widget.original_widget.body[-1])
  widget.original_widget.set_focus(len(widget.original_widget.body) + 1)

def do_general(kv, ret, widget):
  debug("Entering general mode")
  setup_general_hooks()

def do_pipe_prompt(kv, ret, widget):
  debug("ENTERING PIPE MODE")
  kv.open_command_line('!')
def do_search_prompt(kv, ret, widget):
  debug("ENTERING SEARCH MODE")
  kv.open_command_line('/')

def do_command_prompt(kv, ret, widget):
  debug("ENTERING COMMAND MODE")
  kv.open_command_line(':')

def handle_command(prompt, command):
  debug("Handling command", prompt, command)
  if prompt == '/':
    kv.find_and_focus(command)
  if prompt == ':':
    kv.display_status_msg('Sorry, command mode is not yet implemented')
  else:
    kv.display_status_msg('Sorry, %s mode is not yet implemented' % (prompt))

def do_command_entered(kv, ret, widget):
  if kv.in_command_prompt:
    cmd, opts = kv.prompt.get_text()
    kv.prompt.set_edit_text('')
    handle_command(kv.prompt_mode, cmd)

  kv.close_command_line()

def do_open_help(kv, ret, widget):
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
  ":" : {
    "fn" : do_command_prompt,
    "help" : "Enter command mode",
  },
  "/" : {
    "fn" : do_search_prompt,
    "help" : "Enter interactive search"
  },
  "!" : {
    "fn" : do_pipe_prompt,
    "help" : "Pipe kits window to another command"
  },
  "q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "Quit kit / Close current overlay"
  },
  "s" : {
    "fn" : do_interactive_sed,
    "help" : "Open interactive sed editor"
  },
  "p" : {
    "fn" : do_print,
    "help" : "Print window to another command"
  },
  "c" : {
    "fn" : do_syntax_coloring,
    "help" : "turn on syntax highlights"
  },
  "f" : {
    "fn" : do_get_files,
    "help" : "dump the files from the current buffer"
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
  "n" : {
    "fn" : do_next_search,
    "help" : ""
  },
  "N" : {
    "fn" : do_prev_search,
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
    "help" : ""
  },
  "enter" : {
    "fn" : do_command_entered,
    "help" : ""
  }
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
  ('banner', 'black', 'white'),
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

# {{{ main viewer class


_key_hooks = CURSES_HOOKS
class Viewer(object):

  def __init__(self, *args, **kwargs):
    self.after_urwid = []
    self.in_command_prompt = False
    self.prompt_mode = ""
    self.last_search = ""
    self.last_search_index = 0
    self.last_search_token = None
    self.clear_edit_text = False

  def run(self, stdscr):
    ret = read_lines(None)
    self.ret = ret

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


      if self.clear_edit_text:
        self.prompt.set_edit_text("")
        self.prompt.set_caption("")
        self.clear_edit_text = False

      for key in keys:
        if not unhandle_input(key):
          unhandled.append(key)

      if was_general:
        _key_hooks = CURSES_HOOKS
        return []

      return unhandled

    def unhandle_input(key):
      if self.in_command_prompt:
        if key == 'enter':
          do_command_entered(kv, self.ret, widget)
          return True

        if key == 'esc':
          self.close_command_line()
          return True

        return

      if key in _key_hooks.keys():
        debug("KEY ", key, "PRESSED")
        _key_hooks[key]['fn'](self, self.ret, widget)
        return True

    add_vim_movement()
    widget = OverlayStack(urwid.Text(""))

    self.prompt = urwid.Edit()
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line = urwid.WidgetPlaceholder(prompt_cols)
    self.window = widget

    self.panes = urwid.Frame(widget, footer=self.command_line)
    display_lines(ret["lines"], widget)

    loop = urwid.MainLoop(self.panes, palette, unhandled_input=unhandle_input, input_filter=handle_input)

    self.display_status_msg(('banner', "Welcome to the qitchen sink pager. Press '?' for keybindings"))
    if ret['has_content']:
      loop.run()


  def open_command_line(self, mode=':'):
    self.prompt_mode = mode
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = True
    self.panes.set_focus('footer')
    self.prompt.set_edit_text("")

  def close_command_line(self, mode=':'):
    self.prompt.set_edit_text("")
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(" ")), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = False
    self.panes.set_focus('body')

  def find_and_focus(self, word=None, reverse=False):
    start_index = 0
    if not word:
      word = self.last_search

    if self.last_search == word:
      start_index = self.last_search_index

    self.last_search = word

    tokens = self.window.original_widget.body
    def find_word(tokens, start_index):
      found = False

      tokens = tokens[start_index:]

      if self.last_search_token:
        text, opts = self.last_search_token.get_text()
        self.last_search_token.set_text((None, text))

      for index, tok in enumerate(tokens):
        text, opts = tok.get_text()
        if text.find(word) >= 0:
          debug("FOUND WORD", text)
          self.window.original_widget.set_focus_valign('middle')
          self.last_search_index = start_index + index
          self.last_search_token = tok

          found = True
          break

      if found:
        found_text = self.last_search_token.get_text()[0]
        debug("INDEX OF", found_text, "IS", self.last_search_index)
        self.window.original_widget.set_focus(self.last_search_index)
        self.last_search_token.set_text(('banner', text))
      return found

    found = find_word(tokens, start_index + 1)
    if not found:
      kv.display_status_msg("Pattern not found. Wrapping")
      found = find_word(tokens, 0)

      if not found:
        kv.display_status_msg("Pattern not found  (Press RETURN)")


  def display_status_msg(self, msg):
    if type(msg) is str:
      msg = ('banner', msg)
    self.prompt.set_caption(msg)
    self.prompt.set_edit_text("")
    self.clear_edit_text = True

if __name__ == "__main__":
  kv = Viewer()
  curses.wrapper(kv.run)
  for after in kv.after_urwid:
    if hasattr(after, '__call__'):
      try:
        after()
      except Exception, e:
        raise e
# }}}
