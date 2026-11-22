{
    "name": "School Documents",
    "version": "19.0.0.7.0",
    "category": "School",
    "summary": "Shared files for a small school: schoolwide reference folders, "
               "a folder per school year and homeroom, and files on the student record",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Documents for the school addons. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["horizonforge_school_core", "web"],
    "data": [
        "security/school_documents_security.xml",
        "security/ir.model.access.csv",
        "data/school_documents_data.xml",
        "wizard/school_document_upload_views.xml",
        "views/school_document_views.xml",
        "views/school_student_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/school_documents_demo.xml",
    ],
    "installable": True,
}
