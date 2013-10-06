#!/usr/bin/env python
# -*- coding: latin-1 -*-

# {{{ about
# The kitchen sink is a smarter pager. It lets you operate on any output and quickly take action

# DONE
# x locate (and open) files in the output
# x open urls from the output
# x preliminary terminal color support
# x add syntax highlighting to any output
# x add syntax highlighting to git diffs
# x open the output in an external editor
# x locate urls in the output
# x search next word
# x search prev function
# x create a stack for jumping between opened buffers
# x pipe buffer into a command and re-open pager on new output
# x yank the output into xsel buffer
# o compare two different outputs (current buffer and xsel sound good to me)

# TODO

# o MATH
# o sum a column
# o sum a row
# o generate a histogram
# o calculate the big stats (avg, mean, etc)

# }}}

# {{{ imports
import curses
import collections
import itertools
import os
import re
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
def consume(iterator, n):
  '''Advance the iterator n-steps ahead. If n is none, consume entirely.'''
  collections.deque(itertools.islice(iterator, n), maxlen=0)


def clear_escape_codes(line):
  # clear color codes
  newline = re.sub('\033\[\d*;?\d*m', '', line)
  # jank escape code clearing methodology. need to update as new codes found
  newline = re.sub('\033\[\d*[ABCDEFGHIJK]', '', newline)
  return newline

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
  # http://redd.it (example URL)
  all_tokens = []
  for index, line in enumerate(lines):
    col = 0

    while col < len(line) and line[col] == " ":
      col += 1

    tokens = line.split()
    for token in tokens:
      all_tokens.append({
        "text" : clear_escape_codes(token),
        "line" : index,
        "col" : col
      })

      col += len(token) + 1
  return all_tokens

def read_lines(in_lines=None):
  maxx = 0
  numlines = 0
  content = False

  if not in_lines:
    in_lines = list(sys.stdin.readlines())

  lines = []
  for line in in_lines:
    maxx = max(maxx, len(line))
    if line.count("\n"):
      numlines += line.count("\n")
    else:
      numlines += 1
    # strip some stuff out
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
def get_content_from_editor(initial=""):
    from subprocess import call
    from tempfile import NamedTemporaryFile

    editor = os.environ.get('EDITOR', 'vim')
    tfName = None

    initial = clear_escape_codes(initial)
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

# {{{ TextBox widget
class TextBox(urwid.ListBox):
  def __init__(self, *args, **kwargs):
    self.last_focused_lines = []
    return super(TextBox, self).__init__(*args, **kwargs)

  def render(self, size, focus=False):
    self.highlight_middle(size, focus)
    return super(TextBox, self).render(size, focus)

  def get_middle_index(self):
    return self.middle_position

  def get_bottom_index(self):
    return self.bottom_position

  def get_top_index(self):
    return self.top_position

  def highlight_middle(self, size, focus):
    vis = self.calculate_visible(size, focus)

    top_trimmed_rows = vis[1][1]
    bot_trimmed_rows = vis[2][1]


    # Figure out what the middle line is, so we can highlight it
    start_index = 0
    top_visible = None
    bottom_visible = None
    end_index = None
    if top_trimmed_rows:
      top_visible = top_trimmed_rows[-1]
      start_index = top_visible[1]
      end_index = size[1] + start_index

    if bot_trimmed_rows:
      bottom_visible = bot_trimmed_rows[-1]
      end_index = bottom_visible[1]
      if not start_index:
        start_index = end_index - size[1]

    end_index = end_index or size[1]
    self.top_position = start_index
    self.bottom_position = end_index

    middle = abs(end_index - start_index) / 2 + start_index

    self.middle_position = middle
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

    modal_keys.update({ "q" : CURSES_HOOKS['q'], "esc" : CURSES_HOOKS['esc'], "backspace" : CURSES_HOOKS['esc'] })
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
      self.widget = widget
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

def overlay_menu(widget, title="", items=[], focused=None, cb=None, modal_keys=None):
  def button(text, value):
    def button_pressed(but):
      debug("BUTTON PRESSED", title, text)
      cb(text)

    button = urwid.Button(text[:40], on_press=button_pressed)
    button.button_text = value

    return button

  walker = urwid.SimpleListWalker([button(token, token) for token in items])
  listbox = urwid.ListBox(walker)
  url_window = urwid.LineBox(listbox)

  for index, token in enumerate(walker):
    if token.button_text == focused:
      # Need to account for the insertion of the title at the start (below), so
      # we add 1
      listbox.set_focus(index+1)
  walker.insert(0, urwid.Text(title))

  widget.open_overlay(url_window, modal_keys=modal_keys)

def do_syntax_coloring(kv, ret, widget):
  kv.toggle_syntax_coloring()

def iterate_and_match_tokens(tokens, focused_line_no, func):
  files = []
  visited = {}
  cur_closest_distance = 10000000000000
  closest_token = None

  for token in tokens:
    text = token['text']
    if not text in visited:
      visited[text] = True

      ret = func(text, visited)
      if ret:
        closeness = abs(focused_line_no - token['line'])
        if closeness < cur_closest_distance:
          cur_closest_distance = closeness
          closest_token = ret
          debug("SETTING CLOSEST TOKEN", closeness, closest_token)
        files.append(ret)

  return (files, closest_token)

CHECKED_GIT = {}
def is_git_like(obj):
  if obj in CHECKED_GIT:
    return CHECKED_GIT[obj]

  with open(os.devnull, "w") as fnull:
    ret = subprocess.call(['git', 'show', obj], stdout=fnull, stderr=fnull)
    CHECKED_GIT[obj] = ret == 0

  return CHECKED_GIT[obj]

def do_get_git_objects(kv, ret, widget):
  def git_matcher(filename, visited):
    if re.search('^\w*\d*\w\d(\d|\w)+$', filename):
      if is_git_like(filename):
        return filename[:10]

  focused_line = kv.window.original_widget.get_middle_index()
  files, closest_token = iterate_and_match_tokens(ret['tokens'], focused_line, git_matcher)

  if not len(files):
    files.append("No git objects found in document")

  def func(response):
    contents = subprocess.check_output(['git', 'show', response])
    lines = [contents]
    widget.close_overlay()
    kv.read_and_display(lines)

  overlay_menu(widget, title="Choose a git object to open", items=files, cb=func, focused=closest_token)



CHECKED_FILES = {}
def do_get_files(kv, ret, widget):

  def check_file(filename, line_no):
    numberedname = filename + ":" + str(line_no)

    if not numberedname in CHECKED_FILES:
      CHECKED_FILES[numberedname] = os.path.isfile(filename)

    if CHECKED_FILES[numberedname]:
      return numberedname
    else:
      return

  def file_matcher(text, visited):
    dir_text = text
    colon_text = text
    line_no = 0

    while dir_text:
      if not dir_text in visited:
        visited[dir_text] = True
        filename = check_file(dir_text, line_no)
        if filename:
          return filename

      text_dirs = dir_text.split('/')
      text_dirs.pop(0)
      dir_text = '/'.join(text_dirs)

    while colon_text:
      if not colon_text + ":" + str(line_no) in visited:
        visited[colon_text + str(line_no)] = True
        if check_file(colon_text, line_no):
          return colon_text + ":" + str(line_no)

      text_dirs = colon_text.split(':')
      line_no = text_dirs.pop()
      try:
        line_no = int(line_no)
      except:
        line_no = 0

      colon_text = ':'.join(text_dirs)

  focused_line = kv.window.original_widget.get_middle_index()
  files, closest_token = iterate_and_match_tokens(ret['tokens'], focused_line, file_matcher)

  def func(response):
    split_resp = response.split(':')
    line_no = 0
    if len(split_resp) == 2:
      response, line_no = split_resp
    try:
      with open(response, "r") as f:
        contents = list(f.readlines())
        widget.close_overlay()
        kv.read_and_display(contents)
    except Exception, e:
      debug("EXCEPTION", e)

    kv.window.original_widget.set_focus(int(line_no))
  if not len(files):
    files.append("No Files found in buffer")

  def open_in_editor(kv, ret, widget):
    box = kv.window.widget.original_widget
    button, index = box.get_focus()

    # assuming first line is not a file
    if not index:
      return

    filename = button.button_text
    split_resp = filename.split(':')
    line_no = 0
    if len(split_resp) == 2:
      filename, line_no = split_resp
    subprocess.call([os.environ['EDITOR'], filename])

    widget.close_overlay()

  modal_keys = {
    "e" : {
      "fn" : open_in_editor,
      "help" : "",
    }
  }
  overlay_menu(widget, title="Choose a file to open", items=files,
    cb=func, focused=closest_token, modal_keys=modal_keys)

def do_get_urls(kv, ret, widget=None):
  tokens = ret['tokens']

  def url_matcher(text, visited):
    match = re.search("^\W*(https?://[\w\./]*|www.[\w\./\?&\.]*)", text)
    if match:
      return match.group(1)

  def func(response):
    if not response.startswith('http'):
      response = "http://%s" % response
    subprocess.Popen(["/usr/bin/xdg-open", response])
    widget.close_overlay()

  focused_line = kv.window.original_widget.get_middle_index()
  urls, closest_token = iterate_and_match_tokens(ret['tokens'], focused_line, url_matcher)
  if not len(urls):
    urls.append("No URLs found in buffer")
  overlay_menu(widget, title="Choose a URL to open", items=urls, cb=func, focused=closest_token)

def do_print(kv, ret, scr):
  def func():
    print ret['joined']

  kv.after_urwid.append(func)
  raise urwid.ExitMainLoop()

def do_back_or_quit(kv, ret, widget):
  if widget.overlay_opened:
    widget.close_overlay()
  elif kv.stack:
    kv.restore_last_display()
  else:
    raise urwid.ExitMainLoop()

def do_close_overlay_or_quit(kv, ret, widget):
  if  widget.overlay_opened:
    widget.close_overlay()
  else:
    raise urwid.ExitMainLoop()

def do_quit(kv, ret, scr):
  raise urwid.ExitMainLoop()

def do_pop_stack(kv, ret, scr):
  kv.restore_last_display()

def do_edit_text(kv, ret, widget):
  lines = get_content_from_editor(ret["joined"])
  kv.read_and_display(lines)

def do_diff_xsel(kv, ret, widget):
  import difflib
  lines = [clear_escape_codes(line) for line in kv.ret['lines']]
  args = [ 'xsel' ]
  compare = None

  try:
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    compare = p.communicate()[0].strip()
  except:
    kv.display_status_msg(('diff_del', "xsel is required for diffing buffers"))


  if compare:
    compare_lines = [line + "\n" for line in compare.split("\n")]
    comparison = difflib.unified_diff(
      compare_lines, lines,
      fromfile="clipboard", tofile="buffer")

    kv.read_and_display(list(comparison))

    kv.display_status_msg("displaying diff of the xsel buffer (before) and current buffer (after)")


def do_yank_text(kv, ret, widget):
  lines = [clear_escape_codes(line) for line in kv.ret['lines']]

  debug(lines)

  args = [ 'xsel', '-pi' ]

  try:
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write("".join(lines))

    p.communicate()
    kv.display_status_msg("saved buffer to clipboard")
  except:
    kv.display_status_msg(('diff_del', "xsel is required to save the buffer to a clipboard"))


def do_next_search(kv, ret, widget):
  kv.find_and_focus()

def do_prev_search(kv, ret, widget):
  kv.find_and_focus(reverse=True)

def do_scroll_top(kv, ret, widget):
  widget.original_widget.set_focus_valign('top')
  widget.original_widget.set_focus(0)

def do_scroll_bottom(kv, ret, widget):
  widget.original_widget.set_focus_valign("bottom")
  widget.original_widget.set_focus(len(widget.original_widget.body) + 1)

def do_general(kv, ret, widget):
  debug("Entering general mode")
  setup_general_hooks()

def do_pipe_prompt(kv, ret, widget):
  debug("Entering pipe mode")
  kv.open_command_line('!')

def do_search_prompt(kv, ret, widget):
  debug("Entering search mode")
  kv.open_command_line('/')

def do_command_prompt(kv, ret, widget):
  debug("Entering command mode")
  kv.open_command_line(':')

def handle_command(prompt, command):
  debug("Handling command", prompt, command)
  if prompt == '/':
    kv.find_and_focus(command)
  elif prompt == ':':
    kv.display_status_msg('Sorry, command mode is not yet implemented')
  elif prompt == '!':
    kv.pipe_and_display(command)
  else:
    kv.display_status_msg('Sorry, %s mode is not yet implemented' % (prompt))

def do_command_entered(kv, ret, widget):
  if kv.in_command_prompt:
    cmd, opts = kv.prompt.get_text()
    kv.prompt.set_edit_text('')
    handle_command(kv.prompt_mode, cmd)

  kv.close_command_line()
# }}}

# {{{ help
def do_open_help(kv, ret, widget):
  listitems = []

  helps = []
  shortcuts = []
  for item in sorted(_key_hooks.keys()):
    msg = _key_hooks[item].get('help')
    if msg:
      shortcut = urwid.Text([ " ", ('highlight', item[:9])])
      shortcut.align = "left"
      help_msg = urwid.Text(msg + "  ")
      help_msg.align = "right"

      columns = urwid.Columns([ ("fixed", 10, shortcut), ("weight", 1, help_msg)])
      listitems.append(columns)

  listbox = TextBox(listitems)
  widget.open_overlay(urwid.LineBox(listbox),
    width=("relative", 80), height=("relative", 80))

CURSES_HOOKS = {
  ":" : {
    "fn" : do_command_prompt,
    "help" : "enter command mode",
  },
  "/" : {
    "fn" : do_search_prompt,
    "help" : "enter interactive search"
  },
  "!" : {
    "fn" : do_pipe_prompt,
    "help" : "pipe current buffer through an external command"
  },
  "Q" : {
    "fn" : do_close_overlay_or_quit,
    "help" : "quit kit / close current overlay"
  },
  "q" : {
    "fn" : do_back_or_quit,
    "help" : "close current buffer. if there are no buffers left, quit"
  },
  "p" : {
    "fn" : do_print,
    "help" : "print buffer to stdout and quit"
  },
  "s" : {
    "fn" : do_syntax_coloring,
    "help" : "turn on syntax highlights"
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
  "d" : {
    "fn" : do_diff_xsel,
    "help" : "diff the current buffer with the X clipboard"
  },
  "y" : {
    "fn" : do_yank_text,
    "help" : "save the current buffer to the X clipboard with xsel"
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
  },
  "f" : {
    "fn" : do_get_files,
    "help" : "list the files in current buffer"
  },
  "u" : {
    "fn" : do_get_urls,
    "help" : "list the URLs in the current buffer"
  },
  "o" : {
    "fn" : do_get_git_objects,
    "help" : "list the git objects in the current buffer"
  },
  "backspace" : {
    "fn" : do_pop_stack,
    "help" : "visit previously opened buffer"
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
  },
}

for hook in GENERAL_HOOKS:
  def build_replacement():
    obj = GENERAL_HOOKS[hook]

    def replacement(*args, **kwargs):
      global _key_hooks
      obj['oldfn'](*args, **kwargs)
      _key_hooks = CURSES_HOOKS

    obj['oldfn'] = obj['fn']
    obj['fn'] = replacement

  build_replacement()


def setup_general_hooks():
  global _key_hooks
  _key_hooks = GENERAL_HOOKS

# }}}

# {{{ color setup
palette = [
  ('highlight', 'white', 'dark gray'),
  ('banner', 'black', 'white'),
  ('default', 'black', 'dark gray'),
  ('diff_add', 'white', 'light green'),
  ('diff_del', 'white', 'light red'),
  ('streak', 'black', 'dark red'),
  ('bg', 'black', 'dark blue'),
]
COLORS = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]
COLOR_NAMES = {
   "black": "black",
   "red": "dark red",
   "green": "dark green",
   "yellow": "brown",
   "blue": "dark blue",
   "magenta": "dark magenta",
   "cyan": "dark cyan",
   "white" : "white"

}
for color in COLORS:
  palette.append(('%s_bg' % (color), 'black', COLOR_NAMES[color]))
  palette.append(('%s_fg' % (color), COLOR_NAMES[color], 'black'))

  for jcolor in COLORS:
    palette.append(('%s_%s' % (color, jcolor), COLOR_NAMES[color], COLOR_NAMES[jcolor]))


# }}}

# {{{ main viewer class


_key_hooks = CURSES_HOOKS
class Viewer(object):

  def __init__(self, *args, **kwargs):
    self.after_urwid = []
    self.in_command_prompt = False
    self.prompt_mode = ""
    self.last_search = ""
    self.stack = []
    self.working = False
    self.last_search_index = 0
    self.last_search_token = None
    self.clear_edit_text = False
    self.syntax_colored = False

  def update_pager(self):
    debug("UPDATING PAGER")

    try:
      # This can throw if we aren't in text editing mode
      middle_line = self.window.original_widget.get_middle_index()
      start_line = self.window.original_widget.get_top_index() + 1
      end_line = self.window.original_widget.get_bottom_index() + 1
    except Exception, e:
      debug("UPDATE PAGER EXCEPTION", e)
      return

    line_count = self.ret['maxy']
    fraction = min(float(middle_line) / float(line_count) * 100, 100)

    line_no = middle_line
    if fraction < 20:
      fraction = max(float(start_line) / float(line_count) * 100, 0)
      line_no = start_line

    if fraction > 20:
      fraction = min(float(end_line) / float(line_count) * 100, 100)
      line_no = end_line
    fraction = int(fraction)

    line_no = min(end_line, line_count)

    pager_msg = "%s/%s (%s%%)" % (line_no, line_count, fraction)
    if self.working:
      pager_msg = "(working)\n%s" % pager_msg
    self.display_pager_msg(pager_msg)

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

      self.loop.event_loop.alarm(0.05, self.update_pager)
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

    self.command_line = urwid.WidgetPlaceholder(urwid.Text(""))
    self.window = widget

    self.panes = urwid.Frame(widget, footer=self.command_line)
    self.display_lines(ret["lines"])

    self.pager = urwid.Text("")
    self.prompt = urwid.Edit()

    self.open_command_line()
    self.close_command_line()
    self.loop = urwid.MainLoop(self.panes, palette, unhandled_input=unhandle_input, input_filter=handle_input)

    self.display_status_msg(('banner', "Welcome to the kitchen sink pager. Press '?' for shortcuts"))
    if ret['has_content']:
      try:
        self.loop.run()
      except KeyboardInterrupt:
        pass

  def repaint_screen(self):
    self.loop.draw_screen()

  def open_command_line(self, mode=':'):
    self.prompt_mode = mode
    prompt_cols = urwid.Columns([ ("fixed", 1, urwid.Text(self.prompt_mode)), ("weight", 1, self.prompt)])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = True
    self.panes.set_focus('footer')
    self.prompt.set_edit_text("")

  def close_command_line(self, mode=':'):
    self.prompt.set_edit_text("")
    prompt_cols = urwid.Columns([
      ("fixed", 1, urwid.Text(self.prompt_mode)),
      ("weight", 1, self.prompt),
      ("fixed", 25, urwid.Padding(self.pager, align=('relative', 90), min_width=25)),
    ])
    self.command_line.original_widget = prompt_cols
    self.in_command_prompt = False
    self.panes.set_focus('body')

  def escape_ansi_colors(self, lines):
    wlist = []
    def build_color_table():
      table = {"[0":'default'}

      for index, color in enumerate(COLORS):
        table["[%s" % (30 + index)] = "%s_fg" % color
        table["[1;%s" % (30 + index)] = "%s_fg" % color
      for index, color in enumerate(COLORS):
        table["[%s" % (40 + index)] = "%s_bg" % color
        table["[%s" % (40 + index)] = "%s_bg" % color
      for index, color in enumerate(COLORS):
        for jindex, jcolor in enumerate(COLORS):
          table["[%s;%s" % (30+index, 40 + jindex)] = "%s_%s" % (color, jcolor)

      return table


    table = build_color_table()
    for line in lines:
      col = 0
      stripped = line.lstrip()
      col = len(line) - len(stripped)
      markup = []
      stripped = line.rstrip()
      newline = False
      if not self.syntax_colored:
        if stripped.find("\033") >= 0:
          split_strip = stripped.split("\033")
          markup.append(split_strip[0])
          for at in split_strip[1:]:

            # Try colors
            split_at = at.split("m",1)

            if len(split_at) > 1:
              attr, text = split_at
            else:
              # If not a color but an escape code, just swallow it
              text = at
              split_index = re.search("[KABCDEF]", text).start()
              if split_index >= 0:
                split_at = [at[:split_index+1], at[split_index+1:]]

                if len(split_at) > 1:
                  text = split_at.pop()

              attr = None

            if text:
              if attr in table:
                markup.append((table[attr], text))
              else:
                markup.append((None, text))
        else:
          markup = stripped

        line = markup
        if not line:
          newline = True

      else:
        line = (None, line)

      if line:
        wlist.append(urwid.Text(line))
      if newline:
        wlist.append(urwid.Text(''))
    return wlist

  def display_lines(self, lines):
    self.syntax_colored = False
    self.previous_widget = None

    widget = self.window

    wlist = self.escape_ansi_colors(lines)
    walker = urwid.SimpleListWalker(wlist)
    text = TextBox(walker)
    widget.original_widget = text

  def get_focus_index(self, widget):
    rows = self.ret['maxy']
    offset, inset = widget.get_focus_offset_inset((1, rows))
    focus_widget, focus_index = widget.get_focus()

    return focus_index, offset

  def readjust_display(self, listbox, focused_index):
    index, offset = focused_index
    if self.last_search_token:
      text, attr = self.last_search_token.get_text()
      self.last_search_token.set_text((None, text))
      self.last_search_token = listbox.body[self.last_search_index]
      new_text, attr = self.last_search_token.get_text()
      self.last_search_token.set_text(('highlight', new_text))

    listbox.set_focus(index)
    listbox.set_focus_valign(('fixed top', offset))
    self.update_pager()

  def read_and_display(self, lines):
    self.stack.append(self.ret)
    self.ret['focused_index'] = self.get_focus_index(self.window.original_widget)

    self.ret = read_lines(lines)
    self.display_lines(lines)

  def restore_last_display(self):
    if self.stack:
      self.ret = self.stack.pop()

      self.display_lines(self.ret['lines'])
      if 'focused_index' in self.ret:
        self.readjust_display(self.window.original_widget, self.ret['focused_index'])

  def pipe_and_display(self, command):
    import shlex
    data_in = self.ret['joined']
    args = shlex.split(command)
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(data_in)

    stdout = p.communicate()[0]
    kv.read_and_display(stdout.split("\n"))

  def find_and_focus(self, word=None, reverse=False):
    start_index = 0
    focused_widget, focused_index = self.window.original_widget.get_focus()
    start_index = focused_index

    if not word:
      word = self.last_search

    self.last_search = word

    tokens = self.window.original_widget.body
    def find_word(tokens, start_index):
      found = False

      if reverse:
        tokens = tokens[:start_index-1]
      else:
        tokens = tokens[start_index:]

      if self.last_search_token:
        text, opts = self.last_search_token.get_text()
        self.last_search_token.set_text((None, text))

      enum_tokens = enumerate(tokens)
      if reverse:
        enum_tokens = list(reversed(list(enumerate(tokens))))

      word_re = re.compile(word)
      for index, tok in enum_tokens:
        text, opts = tok.get_text()
        if word_re.search(text):
          debug("FOUND WORD", word, "IN", text)
          self.window.original_widget.set_focus_valign('middle')

          self.last_search_index = start_index + index
          if reverse:
            self.last_search_index = index
          self.last_search_token = tok

          found = True
          break

      if found:
        found_text = self.last_search_token.get_text()[0]
        debug("INDEX OF", found_text, "IS", self.last_search_index)
        self.window.original_widget.set_focus(self.last_search_index)
        self.last_search_token.set_text(('highlight', text))
      return found

    found = find_word(tokens, start_index + 1)
    if not found:
      kv.display_status_msg("Pattern not found. Wrapping")
      found = find_word(tokens, 0)

      if not found:
        kv.display_status_msg("Pattern not found  (Press RETURN)")

  def syntax_msg(self):
    if self.syntax_colored:
      self.display_status_msg("Setting syntax to %s" % self.syntax_lang)
    else:
      self.display_status_msg("Disabling syntax coloring")

  def toggle_syntax_coloring(self):
    # a shortcut
    if self.previous_widget:
      original_text = self.window.original_widget
      focused_index = self.get_focus_index(original_text)
      self.window.original_widget = self.previous_widget
      self.previous_widget = original_text

      debug("SYNTAX COLORING PREV WIDGET")

      self.syntax_colored = not self.syntax_colored
      self.readjust_display(self.window.original_widget, focused_index)
      self.syntax_msg()

      return

    self.enable_syntax_coloring()


  # one time setup for syntax coloring
  def enable_syntax_coloring(self):
    debug("INITIALIZING SYNTAX COLORED WIDGET")
    walker = urwid.SimpleListWalker([])

    self.previous_widget = self.window.original_widget
    listbox = TextBox(walker)
    self.window.original_widget = listbox
    self.syntax_colored = True
    focused_index = self.get_focus_index(self.previous_widget)

    formatter = UrwidFormatter()
    def handle_token(token, formatted_line, newline, diff=False):
      text = token[1]
      if not text:
        return newline

      if newline and diff and False:
        if text[0] == '+':
          formatted_line.append(('diff_add', '+'))
          text = token[1][1:]
          token = (token[0], text)
        elif text[0] == '-':
          formatted_line.append(('diff_del', '-'))
          text = token[1][1:]
          token = (token[0], text)

      if text.find('\n') >= 0:
        split_line = clear_escape_codes(text)
        while split_line:
          n = split_line.find('\n')
          if n >= 0:
            newline = True
            last_word = split_line[:n]
            split_line = split_line[n+1:]
            formatted_line.append('')
            walker.append(urwid.Text(list(formatted_line)))
            del formatted_line[:]
          else:
            formatted_line.append((token[0], split_line))
            break
      else:
        token = (token[0], clear_escape_codes(token[1]))
        formatted_line.append(token)
        newline = False

      return newline
      # end of handle_token function

    def add_diff_lines_to_walker(lines, walker, clear_walker=True, cb=None):
      if clear_walker:
        walker[:] = [ ]

      wlines = []
      lexer = None
      fname = None

      iterator = iter(lines)
      index = 0
      for line in iterator:
        index += 1
        line = clear_escape_codes(line)

        if line.startswith("diff --git"):

          reg_lines = [ line ]
          def add_line():
            reg_lines.append(clear_escape_codes(iterator.next()))

          add_line()
          add_line()
          add_line()

          index += 3

          # Look upwards for the commit line (find the first line that starts with Author and Date)
          # and put them in reg_lines

          author_index = 1
          for windex, wline in enumerate(wlines):
            if wline.startswith("Author"):
              author_index = windex

          reg_lines = wlines[author_index-1:] + reg_lines
          wlines = wlines[:author_index-1]

          if wlines:
            add_lines_to_walker(wlines, walker, fname, diff=True)
            add_lines_to_walker(["\n"], walker, fname, diff=False)

          if reg_lines:
            add_lines_to_walker(reg_lines, walker, "text.txt", diff=False)

          # next output
          fname = line.split().pop()
          wlines = [ ]

          def future_call(loop, user_data):
            lines, walker = user_data
            self.working = True
            self.update_pager()
            add_diff_lines_to_walker(lines, walker, clear_walker=False, cb=cb)
            self.working = False

          next_lines = lines[index:]

          return self.loop.set_alarm_in(0.0001, future_call, user_data=(next_lines, walker))
        else:
          wlines.append(line)

      # When we make it to the way end, put the last file contents in
      add_lines_to_walker(wlines, walker, fname, diff=True)
      self.working = False

      if cb:
        cb()

      # This is when we are finally done. (For reals)
      self.update_pager()

    def add_lines_to_walker(lines, walker, fname=None, diff=False):
      if len(lines):
        output = "".join(lines)
        lexer = None

        try:
          lexer = pygments.lexers.guess_lexer_for_filename(fname, output)
        except:
          pass

        if not lexer:
          lexer = guess_lexer(output)

        score = lexer.__class__.analyse_text(output)
        if diff:
          kv.syntax_lang = "git diff"
          debug("LEXER (FORCED) SCORE", lexer, score)
        else:
          kv.syntax_lang = lexer.name
          debug("LEXER (GUESSED) SCORE", lexer, score)
          if score <= 0.1:
            # COULDNT FIGURE OUT A GOOD SYNTAX HIGHLIGHTER
            # DISABLE IT
            lexer = pygments.lexers.get_lexer_by_name('text')
            kv.syntax_lang = "none. (Couldn't auto-detect a syntax)"

            lines = self.escape_ansi_colors([line.rstrip() for line in lines])
            walker.extend(lines)
            return

        tokens = lexer.get_tokens(output)

        # Build the syntax output up line by line, so that it can be highlighted
        # one line at a time
        formatted_tokens = list(formatter.formatgenerator(tokens))
        formatted_line = []
        newline = False

        for token in formatted_tokens:
          newline = handle_token(token, formatted_line, newline, diff)

        if formatted_line:
          walker.append(urwid.Text(list(formatted_line)))


    lines = self.ret['lines']
    if self.ret['joined'].find("diff --git") >= 0:
      def make_cb():
        started = time.time()
        def func():
          ended = time.time()
          debug("TIME TOOK", ended - started)
          if ended - started < 1:
            self.readjust_display(self.window.original_widget, focused_index)

          self.update_pager()

        return func
      add_diff_lines_to_walker(lines, walker, cb=make_cb())
    else:
      wlines = [clear_escape_codes(line) for line in lines]
      add_lines_to_walker(wlines, walker, None)

    self.syntax_msg()


  def display_status_msg(self, msg):
    if type(msg) is str:
      msg = ('highlight', msg)
    self.prompt.set_caption(msg)
    self.prompt.set_edit_text("")
    self.clear_edit_text = True

  def display_pager_msg(self, msg):
    if type(msg) is str:
      msg = ('highlight', msg)
    self.pager.set_text(msg)

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

# vim: set foldmethod marker
