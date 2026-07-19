DEFAULT_CATEGORIES = [
    "Income",
    "Housing",
    "Food",
    "Dining",
    "Utilities",
    "Transport",
    "Travel",
    "Health",
    "Shopping",
    "Subscriptions",
    "Insurance",
    "Savings",
    "Debt",
    "Entertainment",
    "Education",
    "Childcare",
    "School Fees",
    "Medical",
    "Payroll",
    "Vendors",
    "Taxes",
    "Reimbursements",
    "Uncategorized",
]

DEFAULT_RULES = [
    ("contains", "salary", "Income"),
    ("contains", "payroll", "Income"),
    ("contains", "freelance", "Income"),
    ("contains", "rent", "Housing"),
    ("contains", "mortgage", "Housing"),
    ("contains", "grocery", "Food"),
    ("contains", "market", "Food"),
    ("contains", "restaurant", "Dining"),
    ("contains", "coffee", "Dining"),
    ("contains", "electric", "Utilities"),
    ("contains", "internet", "Utilities"),
    ("contains", "phone", "Utilities"),
    ("contains", "uber", "Transport"),
    ("contains", "insurance", "Insurance"),
    ("contains", "school", "School Fees"),
    ("contains", "tuition", "School Fees"),
    ("contains", "doctor", "Medical"),
    ("contains", "hospital", "Medical"),
    ("contains", "gym", "Health"),
    ("contains", "streaming", "Subscriptions"),
]

APPEARANCE_OPTIONS = {"system", "light", "dark"}
COLOR_THEMES = {"ocean", "emerald", "violet", "rose", "amber", "slate", "midnight", "solar"}
INCOME_EXPENSE_CHARTS = {"line", "area", "bar"}
CATEGORY_CHARTS = {"donut", "bar", "horizontal"}
ANIMATION_LEVELS = {"none", "subtle", "standard", "cinematic"}
WEEK_STARTS = {"sunday", "monday"}
WORKSPACE_TYPES = {"personal", "family", "company", "group"}
MEMBER_ROLES = {"breadwinner", "dependent", "member", "employee", "department", "other"}

# Display/currency conversion options. Amounts are stored in the workspace base currency.
CURRENCY_OPTIONS = {
    "USD": "$",
    "PHP": "₱",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "KRW": "₩",
    "INR": "₹",
    "CAD": "C$",
    "AUD": "A$",
    "NZD": "NZ$",
    "SGD": "S$",
    "HKD": "HK$",
    "THB": "฿",
    "MYR": "RM",
    "IDR": "Rp",
    "VND": "₫",
    "MXN": "MX$",
    "BRL": "R$",
    "CHF": "CHF",
}

FX_CACHE_SECONDS = 60 * 60 * 6
OUROBOROS_ADVISOR_IDENTITY = (
    "I am Ouroboros Advisor, the private financial guide inside Ouroboros Financial Management. "
    "I analyze only the active workspace data available to this app."
)
