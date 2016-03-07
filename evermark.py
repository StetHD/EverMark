#!/usr/bin/env python
# coding: utf-8

import os
import time
import ConfigParser

import markdown2

import evernote.edam.type.ttypes as Types
import evernote.edam.notestore.NoteStore as NoteStore
import evernote.edam.userstore.constants as UserStoreConstants
from evernote.api.client import EvernoteClient


class EverMark(object):
    def __init__(self):
        try:
            cf = ConfigParser.ConfigParser()
            cf.read('conf.ini')
            self.auth_token = cf.get('main', 'auth_token')
            self.account = cf.get('main', 'account')
        except Exception:
            pass

        self._debug = True

        self.client = None
        self.user_store = None
        self.note_store = None

        self.notebooks = []
        self.notebook_names = {}  # {guid: name,}
        self.notebook_guids = []
        self.notes = {}  # {notebook_guid: [{'guid': note_guid, 'title': note_title}, ...]}

    def debug(self, info):
        if self._debug:
            print '[DEBUG] %s' % info

    def login(self):
        self.debug('Start to login.')
        yx = False
        if self.account == 'yinxiang':
            yx = True
        self.client = EvernoteClient(token=self.auth_token, sandbox=False, yinxiang=yx)
        self.user_store = self.client.get_user_store()
        version_ok = self.user_store.checkVersion("Evernote EDAMTest (Python)",
                                                  UserStoreConstants.EDAM_VERSION_MAJOR,
                                                  UserStoreConstants.EDAM_VERSION_MINOR)
        if not version_ok:
            print 'ERROR: Evernote SDK version not up to data.'
            return False
        self.note_store = self.client.get_note_store()
        self.debug('Login succeed.')
        return True

    def sync_status(self):
        self.debug('Start to sync status.')
        self.notebooks = []
        self.notebook_names = {}
        self.notebook_guids = []
        self.notes = {}
        self.sync_notebook_status()
        self.sync_note_status()
        self.debug('End sync status.')

    def sync_notebook_status(self):
        self.debug('Start to sync notebook status.')
        self.notebooks = self.note_store.listNotebooks()
        for notebook in self.notebooks:
            notebook_name = notebook.name.decode('utf-8')
            self.debug(notebook_name + ':' + notebook.guid)
            self.notebook_names[notebook.guid] = notebook_name
            self.notebook_guids.append(notebook.guid)
        self.debug('End sync notebook status.')

    def sync_note_status(self):
        self.debug('Start to sync note status.')
        find_filter = NoteStore.NoteFilter()
        spec = NoteStore.NotesMetadataResultSpec()
        spec.includeTitle = True
        notes = self.note_store.findNotesMetadata(find_filter, 0, 10000, spec)

        for note in notes.notes:
            notebook_guid = note.notebookGuid
            note_title = note.title.decode('utf-8')

            if notebook_guid not in self.notes:
                self.notes[notebook_guid] = []

            self.notes[notebook_guid].append({'guid': note.guid, 'title': note_title})

            # self.debug(note_title + ':' + note.guid)

        self.debug('End sync note status.')

    @staticmethod
    def markdown2html(markdown_str):
        if isinstance(markdown_str, str):
            markdown_str = markdown_str.decode('utf-8')
        html = markdown2.markdown(markdown_str, extras=["tables", "fenced-code-blocks", "cuddled-lists"])
        return html

    @staticmethod
    def text2html(text_str):
        if isinstance(text_str, str):
            text_str = text_str.decode('utf-8')
        text_str.replace('\r', '')
        text_str.replace('\n\n', '<div><br></br></div>')
        text_str.replace('\n', '<br></br>')
        return text_str

    def get_notebook_guid(self, notebook_name):
        for k in self.notebook_names:
            if notebook_name == self.notebook_names[k]:
                return k
        return None

    def is_notebook_exists(self, notebook_name):
        if self.get_notebook_guid(notebook_name):
            return True
        else:
            return False

    def get_note_guid(self, notebook_name, note_title):
        notebook_guid = self.get_notebook_guid(notebook_name)
        if not notebook_guid:
            return None
        for note in self.notes[notebook_guid]:
            if note['title'] == note_title:
                return note['guid']
        return None

    def is_note_exist(self, notebook_name, note_title):
        if self.get_note_guid(notebook_name, note_title):
            return True
        else:
            return False

    def create_notebook(self, notebook_name):
        self.debug('Start to create notebook ' + notebook_name + ' .')
        notebook = Types.Notebook()
        notebook.name = notebook_name
        notebook.defaultNotebook = False
        created_notebook = self.note_store.createNotebook(notebook)
        self.debug('Create notebook succeed.')
        self.notebook_names[created_notebook.guid] = notebook_name
        self.notebook_guids.append(created_notebook.guid)
        self.notes[created_notebook.guid] = []

    def inner_create_note(self, notebook_name, note_title, html):
        note = Types.Note()
        note.title = note_title
        note.content = '<?xml version="1.0" encoding="UTF-8"?>'
        note.content += '<!DOCTYPE en-note SYSTEM ' \
            '"http://xml.evernote.com/pub/enml2.dtd">'
        note.content += '<en-note>'
        note.content += html
        note.content += '</en-note>'
        if isinstance(note.content, unicode):
            note.content = note.content.encode('utf-8')

        notebook_guid = self.get_notebook_guid(notebook_name)
        if not notebook_guid:
            print 'ERROR: In create_note, can not get a notebook named ' + notebook_name
            return False

        note.notebookGuid = notebook_guid
        return note

    def create_note(self, notebook_name, note_title, html):
        self.debug('Start to create note ' + notebook_name + '/' + note_title + '.')
        note = self.inner_create_note(notebook_name, note_title, html)
        created_note = self.note_store.createNote(note)
        self.debug("Successfully created a new note with GUID: " + created_note.guid)
        return True

    def update_note(self, notebook_name, note_title, html):
        self.debug('Start to update note ' + notebook_name + '/' + note_title + '.')
        note = self.inner_create_note(notebook_name, note_title, html)
        updated_note = self.note_store.updateNote(note)
        print "Successfully update note with GUID: ", updated_note.guid
        return True

    def sync_file(self, sub_dir_name, file_name):
        """
        :param sub_dir_name: sub_dir_name -> notebook_name
        :param file_name: file_name -> note_title
        :return: True/False

        Sync a file to Evernote.
        file_name should be title.txt(pure text note) or title.md(markdown note).
        If there's not a notebook named sub_dir_name or note named file_name(without extension), then create one.
        """

        self.debug('Start to sync file ' + sub_dir_name + '/' + file_name + '.')
        arr = file_name.split('.')
        if len(arr) != 2 or arr[1] not in ['txt', 'md']:
            return False

        input_file_path = './' + sub_dir_name + '/' + file_name
        file_content = ''
        with open(input_file_path) as f:
            file_content = f.read()

        notebook_name = sub_dir_name
        note_title = arr[0]
        note_type = arr[1]

        if not self.is_notebook_exists(notebook_name):
            self.create_notebook(notebook_name)

        html = ''
        if note_type == 'md':
            html = self.markdown2html(file_content)
        else:
            html = self.text2html(file_content)

        if self.is_note_exist(notebook_name, note_title):
            self
        else:
            self.create_note(notebook_name, note_title, html)

    def sync(self):
        sub_dirs = os.listdir('.')
        for sub_dir in sub_dirs:
            if '.' in sub_dir or sub_dir in ['img', 'evernote', 'thrift']:
                continue
            files = os.listdir('./'+sub_dir)
            for file in files:
                if '.' not in file:
                    continue
                self.sync_file(sub_dir, file)


def main():
    em = EverMark()
    if not em.login():
        print 'login failed'
        return

    last_sync_status = time.time() - 10000
    last_sync = time.time() - 10000

    while True:
        cur_time = time.time()
        if cur_time - last_sync_status > 1000:
            em.sync_status()
            last_sync_status = cur_time

        cur_time = time.time()
        if cur_time - last_sync > 100:
            em.sync()
            last_sync = cur_time

if __name__ == '__main__':
    main()
