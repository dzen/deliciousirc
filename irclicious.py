#!/usr/bin/env python
"""
Parses irc logs to gather urls,
checks urls against craplist,
identifies poster and tags,
if possible, posts to delicious.
"""

__version__ = "0.02"
__copyright__ = "Copyright (c) 2007 GCU"
__license__ = "BSD"

import sys
import re
import os
import optparse
import yaml
import webbrowser
from urlparse import urlparse
import pprint
import threading

import urwid
import urwid.curses_display

import pydelicious
import urllib2

def getpagetitle(url):
    titre = re.compile(r'<title>(.*?)</title>')
    try:
        furl = urllib2.urlopen(url)
        contenu = furl.read()
        letitre = titre.findall(contenu)
        if letitre:
            return letitre[0]
        else:
            return None
    except:
        return None


class PatternList(object):
    """
    A Patternlist is a list of regular expressions. the 'in' operator
    allows a string to be compared against each expression (using search
    NOT match)
    """
    # source :  python cookbook

    def __init__(self, patterns = []):
        self.patterns = []
        for p in patterns:
            self.add(p)

    def add(self, pattern):
        pat = re.compile(pattern)
        self.patterns.append(pat)

    def __contains__(self, item):
        ret = False
        for p in self.patterns:
            if p.search(item):
                ret= True
                break
        return ret


def filtercrap(line):
    """Return True if line not in crapfile, False otherwise"""
    print 'filtecrap call'
    crap = [url.rstrip() for url in open('crap.txt').readlines() if url[0] !='#']
    crappattern = PatternList(crap)
    return (line not in crappattern)


def crap_patterns_list(conf):
    """returns a build craplist"""
    crap = [url.rstrip() for url in open(conf.get('scraplist')).readlines()
            if url[0] !='#']
    return PatternList(crap)

def url_patterns_list():
    """blahblahblah"""
    return PatternList((r'https?://','www\.'))

def build_synonyms(synfile):
    """ build synonyms dict from textfile"""
    synfile = open(synfile)
    synlists = (line.rstrip().split(',') 
                    for line in synfile if line[0]!='#')
    syndict = {}
    for liste in synlists:
        value = liste[0].strip()
        del liste[0]
        for key in liste:
            syndict[key.strip()] = value
    return syndict


def getfile(infile=None):
    """Return a read-opened file handler, sys.stdin if arg is None"""
    if not infile:
        fin = sys.stdin
    elif isinstance(infile, str):
        fin = open(infile, 'r')
    else:
        fin = infile
    res = fin

    return res

def buildlistfromfile(infile, verbose=True, conf={}):
    """Return a list of lines containing URLs in infile"""
    crap_pattern = crap_patterns_list(conf)
    url_pattern = url_patterns_list()
    synonym = build_synonyms(conf['synonyms'])


    res = [url for url in infile if url in url_pattern]
    res = [url for url in res if url not in crap_pattern]

    lutin = re.compile(r'\d{2}:\d{2} <?[ \+@]?(.*?)>? ')
    url = re.compile(r'(https?://.*?|www\..*?)[ ,)\n]')
    tags = re.compile(r' #(.*?)#[ ,\n]')

    liste = []
    for line in res:
        if verbose:
            print >> sys.stderr, line,
        for i in url.findall(line):
            if i.startswith('www'):
                i = 'http://%s' % i
            # we keep the last instance of a given url in the log
            for k,u in enumerate(liste):
                if u['url']==i:
                    del liste[k]
            d = {}
            d['url'] = i
            taglist = []
            _lut = lutin.findall(line)
            if (len(_lut)):
                taglist.append((synonym.get(_lut[0]) or _lut[0]))
                if tags.findall(line):
                    _tags = tags.findall(line)[0].split(',')
                    _tags = [(synonym.get(tag.lower().strip()) 
                            or tag.lower().strip()) 
                            for tag in _tags]
                    taglist.extend(_tags)
                if len(taglist)>1 and not (set(taglist) & set(conf.get('exclude_tags'))):
                    d['tags'] = taglist
                    liste.append(d)

    return liste

class UrlWidget(urwid.WidgetWrap):
    """URL Widget for urwid"""
    def __init__(self, item, size, unfocused, focused=None):
        self.url = item['url']
        self.title = None
        self.tags = item['tags'] or []
        self.lutin = self.tags[0]
        self.scrapped = False
        self.posted = False
        w = urwid.Text('%1s%1s %s' % ('s'*self.scrapped,
                                    'p'*self.posted,
                                    self.url[:size[0]-3]))
        self.widget = w
        w = urwid.AttrWrap(w, unfocused, focused)
        urwid.WidgetWrap.__init__(self, w)
        self.size = size

    def keypress(self, pos, key):
        return key

    def selectable(self):
        return True

    def post(self):
        """sets tposted"""
        self.posted = not self.posted
        self.widget.set_text('%1s%1s %s' % (\
                'p'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )

    def retag(self):
        """sets taggued"""
        self.scrapped = not self.scrapped
        self.widget.set_text('%1s%1s %s' % (\
                's'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )

    def scrap(self):
        """sets scrapped"""
        self.scrapped = not self.scrapped
        self.widget.set_text('%1s%1s %s' % (\
                's'*self.scrapped,
                'p'*self.posted,
                 self.url[:self.size[0]-3])
        )


class MainWindow(object):
    """Our main window"""

    ui = None
    def __init__(self, conf, urls):
        self.urls = urls
        self.conf = conf
        self.ui = urwid.curses_display.Screen()
        self.scraplist = []
        self.view = None

# {{{ def: build
    def build(self):
        """build the widgetz"""
        self.ui.register_palette([
                ('body', 'black', 'light gray'),
                ('selected', 'white', 'dark blue', 'standout'),
                #('header', 'yellow', 'black', 'standout'),
                ('header', 'black', 'light gray', 'standout'),
        ])
        self.ui.run_wrapper(self.run)
# }}}

# {{{ def: redisplay
    def redisplay(self):
        """if the display iz br0kmut"""
        self.ui.draw_screen(self.size, self.view.render(self.size, focus=1))
# }}}

# {{{ def: run
    def run(self):
        """here we startz"""
        print "started"
        self.size = self.ui.get_cols_rows()
        itemlist = [UrlWidget(line, self.size, None,'selected') for line in urls]
        self.items = urwid.PollingListWalker(itemlist)
        self.listbox = urwid.ListBox(self.items)
        self.instruct = urwid.Text("[v]iew [r]etag [p]ost [s]crap [q]quit")
        self.header = urwid.AttrWrap(self.instruct, 'header')
        self.tagedit = urwid.Edit("")
        self.titledit = urwid.Edit("")
        self.footer = urwid.AttrWrap(self.tagedit,'header')
        self.view = urwid.Frame(self.listbox, self.header, self.footer)

        self.infos = urwid.Overlay(
            urwid.AttrWrap(self.tagedit, 'tags'),
            urwid.AttrWrap(self.titledit, 'title'),
            ('fixed left', 5), 16, ('fixed top', 0), 1 )

        while 1:
            keys = None
            focus, _ign = self.listbox.body.get_focus()
            if focus:
                self.tagedit.set_edit_text('%s' % ', '.join(focus.tags))
                self.tagedit.set_caption('%s\nLutin : %s\nTags : ' %
                    (focus.url[:self.size[0]-2],focus.lutin))
                self.tagedit.set_edit_text('%s' % ', '.join(focus.tags))
                self.footer = urwid.AttrWrap(self.tagedit,'header')
                self.view = urwid.Frame(self.listbox, self.header, self.footer)
                self.redisplay()

            while not keys:
                keys = self.ui.get_input()
            for k in keys:
                if k in ('q','Q'):
                    # quit
                    try:
                        crapfile = open(self.conf.get('scraplist'), 'a+')
                        crapfile.writelines(self.scraplist)
                        crapfile.close()
                    except:
                        pprint.pprint(self.scraplist)
                        pprint.pprint(self.conf.get('scraplist'))
                        pprint.pprint(crapfile)
                    return

                if k in ('s','S'):
                    # scrap
                    self.scrap(focus, self.conf.get('scraplist'))

                if k in ('r','R','enter'):
                    self.retag(focus)

                if k in ('p','P'):
                    self.post(focus)

                if k in ('v','V'):
                    # view
                    webbrowser.open_new_tab(focus.url)
                    self.ui.clear()
                if "window resize" in keys:

                    self.size = self.ui.get_cols_rows()
                    self.redisplay()
                self.view.keypress(self.size, k)
# }}}

# {{{ def: scrap
    def scrap(self, item, liste):
        """adds an item to teh scapz list"""
        item.scrap()

        domain = urlparse(item.url).netloc
        domain = re.escape(domain)
        domain = '%s\n' % domain
        if item.scrapped:
            self.scraplist.append(domain)
        else:
            self.scraplist.remove(domain)
# }}}

# {{{ def: post
    def post(self, item):
        """post teh item at delicious"""
        if not item.title:
            item.title = getpagetitle(item.url) or self.inputwidget("title")
            item.title = unicode(item.title, errors='ignore')

        # launch posting in a new thread ?
        pydelicious.add(
                self.conf.get('login'), self.conf.get('pass'),
                item.url, item.title, tags=' '.join(item.tags))

#        threading.Thread(None, pydelicious.add,
#            (self.conf.get('login'), self.conf.get('pass'), item.url, item.title),
#            {'tags' : ' '.join(item.tags)}).start()

        item.post()

# }}}

# {{{ def get_url_info

    def display_url_info(self, item):
        """shows the url infos in ``statusbar''"""



    def inputwidget(self, caption, keepcontent=False):
        """returns a text entered"""
        old_text = self.tagedit.edit_text
        if not keepcontent:
            self.view.set_focus('footer')
            self.tagedit.edit_text = ""
        self.tagedit.set_edit_pos(len(self.tagedit.edit_text))
        self.tagedit.set_caption('%s: ' % caption)
        self.redisplay()
        while True:
            keys = self.ui.get_input()
            self.redisplay()
            for k in keys:
                if k == "enter":
                    self.view.set_focus('body')
                    ret = self.tagedit.edit_text
                    self.tagedit.edit_text = old_text
                    self.redisplay()
                    return ret
                self.view.keypress(self.size, k)
                self.redisplay()


    def retag(self, item):
        """retags teh current url"""
        self.view.set_focus('footer')
        self.tagedit.set_edit_pos(len(self.tagedit.edit_text)-1)
        tag = self.inputwidget('tags', True).strip()
        item.tags = [s.strip() for s in tag.split(',')]


if __name__ == "__main__":
    # get options from teh command line

    p = optparse.OptionParser(
        description='Parses irc logfile to find urls to be posted to del.icio.us',
        prog='gculicious',
        version='gculicious 0.01',
        usage='gculicious.py logfile',)
    p.add_option(
        '-v', '--verbose', action ='store_true', help='returns original line in addition to filtered elements')
    p.add_option(
        '-c', '--conf', dest="configuration",
        help="configuration file", metavar="CONF")
    options, arguments = p.parse_args()

    if options.verbose:
        pprint.pprint(options)

    if len(arguments) > 1:
        p.print_help()
        exit

    # gets the configuration
    print "Reading config file... "
    config = yaml.load(file(options.configuration or './irclicious.yml'))
    if len(arguments) == 1:
        fich = getfile(arguments[0])
    else:
        fich = getfile()

    # parses the file
    print "Building url list... "
    urls = buildlistfromfile(fich, options.verbose, config)

    # debugging
    if options.verbose:
        pprint.pprint(urls)
        sys.exit(0)

    # launches the curswin
    if len(urls) == 0:
        pprint.pprint('No urls to post today')
        sys.exit(0)
    mw = MainWindow(config, urls)
    mw.build()
