from . import models
from . import wizard


def uninstall_hook(env):
    """Put the schedules and Fill Ahead back on the Gradebook menu."""
    root = env.ref("horizonforge_school_gradebook.menu_school_gradebook_root", raise_if_not_found=False)
    for xmlid, sequence in (("menu_school_assignment_templates", 25), ("menu_school_assignment_generate", 30)):
        menu = env.ref(f"horizonforge_school_gradebook.{xmlid}", raise_if_not_found=False)
        if menu and root:
            menu.write({"parent_id": root.id, "sequence": sequence})
