"""Canonical starter taxonomy seeded into a user's categories on their first
GET /api/categories call (see app/api/categories.py). Seeded rows are
ordinary, fully editable categories afterward (see Category.is_default);
this list only controls what a brand-new user starts with."""

DEFAULT_CATEGORIES: list[dict] = [
    {
        "name": "Income",
        "subcategories": ["Salary", "Investments", "Other Income"],
    },
    {
        "name": "Housing",
        "subcategories": ["Rent & Mortgage", "Utilities", "Home Insurance", "Maintenance"],
    },
    {
        "name": "Food & Dining",
        "subcategories": ["Groceries", "Restaurants & Bars", "Coffee Shops"],
    },
    {
        "name": "Transportation",
        "subcategories": ["Gas & Fuel", "Public Transit", "Parking & Tolls", "Auto Maintenance"],
    },
    {
        "name": "Shopping",
        "subcategories": ["Clothing", "Electronics", "Home Goods"],
    },
    {
        "name": "Entertainment",
        "subcategories": ["Streaming & Subscriptions", "Movies & Events", "Hobbies"],
    },
    {
        "name": "Health & Fitness",
        "subcategories": ["Medical", "Pharmacy", "Gym & Fitness"],
    },
    {
        "name": "Bills & Utilities",
        "subcategories": ["Phone", "Internet", "Insurance"],
    },
    {
        "name": "Travel",
        "subcategories": ["Flights & Hotels", "Transportation"],
    },
    {"name": "Personal Care", "subcategories": []},
    {"name": "Education", "subcategories": []},
    {"name": "Savings & Transfers", "subcategories": []},
    {"name": "Other", "subcategories": []},
]
