#!/usr/bin/env python
"""
Parses irc logs to gather urls,
checks urls against craplist,
identifies poster and tags,
if possible, posts to delicious.
"""

__author__ = "Jean-Charles <anhj> Bagneris"
__version__ = "0.01"
__copyright__ = "Copyright (c) 2007 GCU"
__license__ = "BSD"

import sys
import re
import os
import optparse
import ConfigParser
import webbrowser
from urlparse import urlparse

import urwid
import urwid.curses_display
#kinda gruika

#import deliciousapi as deliciousmodule
#deliciousapi = deliciousmodule.DeliciousAPI()
import deliciousapi

from deliciousapi import DeliciousAPI

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



def filterurl(line):
    """Return True if url in line, False otherwise"""
    url = (r'https?://','www\.')
    urlpattern = PatternList(url)
    return (line in urlpattern)

def filtercrap(line):
    """Return True if line not in crapfile, False otherwise"""
    crap = [url.rstrip() for url in open('crap.txt').readlines() if url[0] !='#']
    crappattern = PatternList(crap)
    return (line not in crappattern)

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

def buildlistfromfile(infile, verbose=True):
    """Return a list of lines containing URLs in infile"""
    res = infile
    for func in (filterurl,filtercrap):
        res = filter(func, res)
    infile.close()

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
            if i in [u['url'] for u in liste]:
                continue
            d = {}
            d['url'] = i
            taglist = []
            _lut = lutin.findall(line)
            if (len(_lut)):
                taglist.append(lutin.findall(line)[0])
                if tags.findall(line):
                    taglist.extend(tags.findall(line)[0].split(','))
                d['tags'] = taglist
                liste.append(d)

    return liste

class UrlWidget(urwid.WidgetWrap):
    """URL Widget for urwid"""
    def __init__(self, item, size, unfocused, focused=None, dh=None):
        self.dh = dh
        self.url = item['url']
        self.tags = item['tags']
        self.lutin = self.tags[0]
        self.scrapped = False
        self.posted = False
        w = urwid.Text('%1s%1s %s' % ('s'*self.scrapped,
                                    'p'*self.posted,
                                    self.url[:size[0]-3]))
        self.widget = w
        w = urwid.AttrWrap(w, unfocused, focused)
        urwid.WidgetWrap.__init__(self, w)

    def keypress(self, pos, key):
        return key

    def selectable(self):

        return True

    def post(self):
        """post this item at loliciouz"""

    def retag(self):
        pass

class MainWindow(object):
    """Our main window"""

    ui = None
    def __init__(self, conf, urls):
        self.urls = urls
        self.conf = conf
        self.ui = urwid.curses_display.Screen()
        self.dh = DeliciousAPI(
                conf.get('delicious', 'login'),
                conf.get('delicious', 'pass'))

        self.view = None

    def build(self):
        """build the widgetz"""
        self.ui.register_palette([
                ('body', 'black', 'light gray'),
                ('selected', 'white', 'dark blue', 'standout'),
                ('header', 'yellow', 'black', 'standout'),
        ])
        self.ui.run_wrapper(self.run)

    def run(self):
        """here we startz"""
        print "started"
        size = self.ui.get_cols_rows()
        itemlist = [UrlWidget(line,size,None,'selected', self.dh) for line in urls]
        self.items = urwid.PollingListWalker(itemlist)
        self.listbox = urwid.ListBox(self.items)
        self.instruct = urwid.Text("[v]iew [r]etag [p]ost [s]crap [q]quit")
        self.header = urwid.AttrWrap(self.instruct, 'header')
        self.tagedit = urwid.Edit("")
        self.footer = urwid.AttrWrap(self.tagedit,'header')
        self.view = urwid.Frame(self.listbox, self.header, self.footer)

        while 1:
            self.ui.draw_screen( size, self.view.render(size, focus=1))
            keys = None
            while not keys:
                keys = self.ui.get_input()
            for k in keys:
                if k in ('q','Q'):
                    # quit
                    crapfile = open('crap.txt','a')
                    crapfile.writelines(scraplist)
                    crapfile.close()
                    return
                if k in ('s','S'):
                    # scrap
                    #scrap(focus, scraplist)
                    pass
                if k in ('r','R','enter'):
                    self.retag()
                if k in ('p','P'):
                    self.dlcpost()
                if k in ('v','V'):
                    # view
                    webbrowser.open_new_tab(focus.url)
                    self.ui.clear()
                if "window resize" in keys:
                    cols, rows = self.ui.get_cols_rows()
                self.view.keypress(size, k)


    def scrap(self, item, liste):
        """adds an item to teh scapz list"""
        item.scrapped = not item.scrapped
        item.widget.set_text('%1s%1s %s' % ('s'*item.scrapped,
                                            'p'*item.posted,
                                            item.url[:size[0]-3]))
        domain = urlparse(item.url).netloc
        domain = re.escape(domain)
        domain = '%s\n' % domain
        if item.scrapped:
            liste.append(domain)
        else:
            liste.remove(domain)


    def retag(self, item):
        view.set_focus('footer')
        tagedit.set_edit_pos(len(tagedit.edit_text))
        while True:
            keys = ui.get_input()
            canvas = view.render(size, focus=True)
            ui.draw_screen(size, canvas )
            for k in keys:
                if k == "enter":
                    view.set_focus('body')
                    item.tags = [s.strip() for s in tagedit.edit_text.split(',')]
                    return
                view.keypress(size,k)


#def run():
#    """Main urwid loop"""
#
#
#
#    def dlcpost(item):
#        if item.posted:
#            return
#        titre = re.compile(r'<title>(.*?)</title>')
#
#        def getpagetitle(url):
#            import urllib2
#            try:
#                furl = urllib2.urlopen(url)
#                contenu = furl.read()
#                letitre = titre.findall(contenu)
#                if letitre:
#                    return letitre[0]
#                else:
#                    letitre = "No description"
#                    return letitre
#            except:
#                return "No description"
#
#        titre = getpagetitle(item.url)
#        deliciousapi.add(dlclogin, dlcpass,
#                        item.url, titre,
#                        tags = ' '.join(item.tags))
#        item.posted = True
#        item.widget.set_text('%1s%1s %s' % ('s'*item.scrapped,
#                                            'p'*item.posted,
#                                            item.url[:size[0]-3]))
#
#
#    while True:
#        focus, _ign = listbox.body.get_focus()
#        tagedit.set_caption('%s\nLutin : %s\nTags : ' %
#                (focus.url[:size[0]-2],focus.lutin))
#        tagedit.set_edit_text('%s' % ', '.join(focus.tags))
#        footer = urwid.AttrWrap(tagedit,'header')
#        view = urwid.Frame(listbox, header, footer)
#        canvas = view.render(size, focus=True)
#        ui.draw_screen(size, canvas)
#        keys = None
#        while not keys:
#            keys = ui.get_input()
#
#        for k in keys:
#            if k in ('q','Q'):
#                # quit
#                crapfile = open('crap.txt','a')
#                crapfile.writelines(scraplist)
#                crapfile.close()
#                return
#            if k in ('s','S'):
#                # scrap
#                scrap(focus, scraplist)
#            if k in ('v','V'):
#                # view
#                webbrowser.open_new_tab(focus.url)
#                ui.clear()
#            if k in ('r','R','enter'):
#                # retag
#                retag(focus)
#            if k in ('p','P'):
#                # post
#                dlcpost(focus)
#            if "window resize" in keys:
#                cols, rows = ui.get_cols_rows()
#            view.keypress(size, k)

if __name__ == "__main__":
    scraplist = []
    p = optparse.OptionParser(
        description='Parses irc logfile to find urls to be posted to del.icio.us',
        prog='gculicious',
        version='gculicious 0.01',
        usage='gculicious.py logfile',)
    p.add_option('-v', '--verbose', action ='store_true', help='returns original line in addition to filtered elements')
    options, arguments = p.parse_args()
    if len(arguments) > 1:
        p.print_help()
        exit
    print "Reading config file... "
    config = ConfigParser.RawConfigParser()
    config.read(['/etc/ircliciousrc',os.path.expanduser('~/.irclicious/config'),
        'ircliciousrc'])
#    dlclogin = config.get('delicious','login')
#    dlcpass = config.get('delicious','pass')
    if len(arguments) == 1:
        fich = getfile(arguments[0])
    else:
        fich = getfile()
    print "Building url list... "
    urls = buildlistfromfile(fich, options.verbose)


    mw = MainWindow(config, urls)
    mw.build()
