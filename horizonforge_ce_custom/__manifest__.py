{
    "name": "HorizonForge CE Customizations",
    "version": "19.0.1.2.0",
    "category": "Hidden/Tools",
    "summary": "Small, safe usability tweaks for Odoo Community: home action, "
               "no quick-create of contacts/products, duplicate contact warning, "
               "no odoo.com phone-home, no public sign-up, optional simple interface for non-admins",
    "author": "Ozark AG LLC",
    "license": "AGPL-3",
    # auth_signup: installed first, so its free sign-up default is turned off after it.
    "depends": ["auth_signup", "base_setup", "mail", "web"],
    "data": [
        "security/hf_security.xml",
        "data/ir_config_parameter_data.xml",
        "views/res_users_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "horizonforge_ce_custom/static/src/js/user_menu.js",
            "horizonforge_ce_custom/static/src/js/simple_interface.js",
            "horizonforge_ce_custom/static/src/xml/navbar.xml",
            "horizonforge_ce_custom/static/src/scss/chat_window.scss",
        ],
    },
    "post_init_hook": "_hf_post_init",
    "installable": True,
}
