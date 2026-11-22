# School Documents

Shared files for a small school on Odoo 19 Community, with the same logins and
groups as the other school addons. Installs on top of `horizonforge_school_core`.

## Folders

| Folder | Who sees and adds to it |
|---|---|
| **School Reference** and the folders inside it (Handbooks and Policies, Forms, Curriculum to start with) | Every teacher, the office, administrators |
| A folder per **school year**, created with the year | Every teacher, the office, administrators |
| Inside each year, a folder per **homeroom** | That homeroom's teacher, the office, administrators |

Anyone who sees a folder can add folders inside it; they are seen by the same
people. The year and homeroom folders follow the names of their year and
homeroom. Moving a file to another folder changes who sees it.

## Files

School, Documents, **Browse** shows the files with the folder tree on the
left. **Upload Files** (in the Documents menu, or on a folder) adds one or
several files at once. Open a file to rename it, add a note, move it or
download it; PDFs and pictures are shown on the page.

Files are kept in Odoo's filestore, so they are part of the Odoo backup. To
change a Word or Excel file, download it, edit it and upload the new version.

## Deleting

Deleting takes two steps on purpose:

1. **Delete** on a file asks for confirmation and moves it to the **Trash**:
   it disappears from everyone's folders but nothing is lost. Anyone who can
   change the file can do this, and restore it.
2. **Delete for Good**, in the trash, erases the file from the server after a
   second confirmation. Only the office and administrators can.

A folder can only be deleted when it is empty (files in the trash count), and
only by the office and administrators.

## Student files

The student form has a **Files** tab for enrollment forms, records and the
like. Whoever can see the student can open them: the office and every
teacher. They are not part of the shared folders.

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_school_documents \
    -i horizonforge_school_documents --test-tags /horizonforge_school_documents --stop-after-init
```
