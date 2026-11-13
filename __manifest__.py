{
    "name": "Cinema POS",
    "version": "19.0.1.0.0",
    "category": "Services/Cinema",
    "summary": "Movies screen for the Point of Sale: pick a showtime and seats, sell tickets with snacks",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "cinema_booking"],
    "data": [
        "security/security.xml",
        "data/params.xml",
        "data/product_data.xml",
        "views/pos_config_views.xml",
        "views/booking_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "cinema_pos_screen/static/src/app/movies_screen.js",
            "cinema_pos_screen/static/src/app/movies_screen.xml",
            "cinema_pos_screen/static/src/app/movies_screen.scss",
            "cinema_pos_screen/static/src/app/control_button.js",
            "cinema_pos_screen/static/src/app/control_button.xml",
        ],
    },
    "installable": True,
    "application": False,
}
