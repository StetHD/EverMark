# EverMark
A tool that can sync local markdown/text notes to **Evernote** .

# Functions

## Sync directories

Sub directories that in the root directory (can be set by user in `conf.ini`) would be synced automatically.

This means, if there is no notebook in **Evernote** has the same name as the sub directory, then **EverMark** will create one.

Users can make **EverMark** not to sync specific sub directories by edit `ignore_dirs` (directory names are splitted by `,`) in `conf.ini`.

## Sync notes

Only files that have `.txt` or `.md` suffix would be synced to **Evernote** .

`txt` represents plain text files。

`md` represents  **MarkDown** files。
