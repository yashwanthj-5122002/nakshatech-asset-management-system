"""ISO 4217 currency reference data used for commercial (BD estimate / client invoice) amounts.

INR is the accounting base currency. The list is a standard reference table, not a
business rule: any code here may be used for a foreign commercial transaction.
"""

from __future__ import annotations

BASE_CURRENCY = "INR"

# code -> (name, minor_units, symbol)
_CURRENCIES: dict[str, tuple[str, int, str]] = {
    "AED": ("UAE Dirham", 2, "AED"), "AFN": ("Afghan Afghani", 2, "AFN"), "ALL": ("Albanian Lek", 2, "ALL"),
    "AMD": ("Armenian Dram", 2, "AMD"), "ANG": ("Netherlands Antillean Guilder", 2, "ANG"), "AOA": ("Angolan Kwanza", 2, "AOA"),
    "ARS": ("Argentine Peso", 2, "ARS"), "AUD": ("Australian Dollar", 2, "A$"), "AWG": ("Aruban Florin", 2, "AWG"),
    "AZN": ("Azerbaijani Manat", 2, "AZN"), "BAM": ("Bosnia-Herzegovina Convertible Mark", 2, "BAM"), "BBD": ("Barbados Dollar", 2, "BBD"),
    "BDT": ("Bangladeshi Taka", 2, "BDT"), "BGN": ("Bulgarian Lev", 2, "BGN"), "BHD": ("Bahraini Dinar", 3, "BHD"),
    "BIF": ("Burundian Franc", 0, "BIF"), "BMD": ("Bermudian Dollar", 2, "BMD"), "BND": ("Brunei Dollar", 2, "BND"),
    "BOB": ("Boliviano", 2, "BOB"), "BRL": ("Brazilian Real", 2, "R$"), "BSD": ("Bahamian Dollar", 2, "BSD"),
    "BTN": ("Bhutanese Ngultrum", 2, "BTN"), "BWP": ("Botswana Pula", 2, "BWP"), "BYN": ("Belarusian Ruble", 2, "BYN"),
    "BZD": ("Belize Dollar", 2, "BZD"), "CAD": ("Canadian Dollar", 2, "C$"), "CDF": ("Congolese Franc", 2, "CDF"),
    "CHF": ("Swiss Franc", 2, "CHF"), "CLP": ("Chilean Peso", 0, "CLP"), "CNY": ("Chinese Yuan", 2, "CN¥"),
    "COP": ("Colombian Peso", 2, "COP"), "CRC": ("Costa Rican Colon", 2, "CRC"), "CUP": ("Cuban Peso", 2, "CUP"),
    "CVE": ("Cape Verdean Escudo", 2, "CVE"), "CZK": ("Czech Koruna", 2, "CZK"), "DJF": ("Djiboutian Franc", 0, "DJF"),
    "DKK": ("Danish Krone", 2, "DKK"), "DOP": ("Dominican Peso", 2, "DOP"), "DZD": ("Algerian Dinar", 2, "DZD"),
    "EGP": ("Egyptian Pound", 2, "EGP"), "ERN": ("Eritrean Nakfa", 2, "ERN"), "ETB": ("Ethiopian Birr", 2, "ETB"),
    "EUR": ("Euro", 2, "€"), "FJD": ("Fijian Dollar", 2, "FJD"), "FKP": ("Falkland Islands Pound", 2, "FKP"),
    "GBP": ("Pound Sterling", 2, "£"), "GEL": ("Georgian Lari", 2, "GEL"), "GHS": ("Ghanaian Cedi", 2, "GHS"),
    "GIP": ("Gibraltar Pound", 2, "GIP"), "GMD": ("Gambian Dalasi", 2, "GMD"), "GNF": ("Guinean Franc", 0, "GNF"),
    "GTQ": ("Guatemalan Quetzal", 2, "GTQ"), "GYD": ("Guyanese Dollar", 2, "GYD"), "HKD": ("Hong Kong Dollar", 2, "HK$"),
    "HNL": ("Honduran Lempira", 2, "HNL"), "HRK": ("Croatian Kuna", 2, "HRK"), "HTG": ("Haitian Gourde", 2, "HTG"),
    "HUF": ("Hungarian Forint", 2, "HUF"), "IDR": ("Indonesian Rupiah", 2, "IDR"), "ILS": ("Israeli New Shekel", 2, "₪"),
    "INR": ("Indian Rupee", 2, "₹"), "IQD": ("Iraqi Dinar", 3, "IQD"), "IRR": ("Iranian Rial", 2, "IRR"),
    "ISK": ("Icelandic Krona", 0, "ISK"), "JMD": ("Jamaican Dollar", 2, "JMD"), "JOD": ("Jordanian Dinar", 3, "JOD"),
    "JPY": ("Japanese Yen", 0, "¥"), "KES": ("Kenyan Shilling", 2, "KES"), "KGS": ("Kyrgyzstani Som", 2, "KGS"),
    "KHR": ("Cambodian Riel", 2, "KHR"), "KMF": ("Comorian Franc", 0, "KMF"), "KPW": ("North Korean Won", 2, "KPW"),
    "KRW": ("South Korean Won", 0, "₩"), "KWD": ("Kuwaiti Dinar", 3, "KWD"), "KYD": ("Cayman Islands Dollar", 2, "KYD"),
    "KZT": ("Kazakhstani Tenge", 2, "KZT"), "LAK": ("Lao Kip", 2, "LAK"), "LBP": ("Lebanese Pound", 2, "LBP"),
    "LKR": ("Sri Lankan Rupee", 2, "LKR"), "LRD": ("Liberian Dollar", 2, "LRD"), "LSL": ("Lesotho Loti", 2, "LSL"),
    "LYD": ("Libyan Dinar", 3, "LYD"), "MAD": ("Moroccan Dirham", 2, "MAD"), "MDL": ("Moldovan Leu", 2, "MDL"),
    "MGA": ("Malagasy Ariary", 2, "MGA"), "MKD": ("Macedonian Denar", 2, "MKD"), "MMK": ("Myanmar Kyat", 2, "MMK"),
    "MNT": ("Mongolian Tugrik", 2, "MNT"), "MOP": ("Macanese Pataca", 2, "MOP"), "MRU": ("Mauritanian Ouguiya", 2, "MRU"),
    "MUR": ("Mauritian Rupee", 2, "MUR"), "MVR": ("Maldivian Rufiyaa", 2, "MVR"), "MWK": ("Malawian Kwacha", 2, "MWK"),
    "MXN": ("Mexican Peso", 2, "MX$"), "MYR": ("Malaysian Ringgit", 2, "MYR"), "MZN": ("Mozambican Metical", 2, "MZN"),
    "NAD": ("Namibian Dollar", 2, "NAD"), "NGN": ("Nigerian Naira", 2, "NGN"), "NIO": ("Nicaraguan Cordoba", 2, "NIO"),
    "NOK": ("Norwegian Krone", 2, "NOK"), "NPR": ("Nepalese Rupee", 2, "NPR"), "NZD": ("New Zealand Dollar", 2, "NZ$"),
    "OMR": ("Omani Rial", 3, "OMR"), "PAB": ("Panamanian Balboa", 2, "PAB"), "PEN": ("Peruvian Sol", 2, "PEN"),
    "PGK": ("Papua New Guinean Kina", 2, "PGK"), "PHP": ("Philippine Peso", 2, "₱"), "PKR": ("Pakistani Rupee", 2, "PKR"),
    "PLN": ("Polish Zloty", 2, "PLN"), "PYG": ("Paraguayan Guarani", 0, "PYG"), "QAR": ("Qatari Riyal", 2, "QAR"),
    "RON": ("Romanian Leu", 2, "RON"), "RSD": ("Serbian Dinar", 2, "RSD"), "RUB": ("Russian Ruble", 2, "RUB"),
    "RWF": ("Rwandan Franc", 0, "RWF"), "SAR": ("Saudi Riyal", 2, "SAR"), "SBD": ("Solomon Islands Dollar", 2, "SBD"),
    "SCR": ("Seychellois Rupee", 2, "SCR"), "SDG": ("Sudanese Pound", 2, "SDG"), "SEK": ("Swedish Krona", 2, "SEK"),
    "SGD": ("Singapore Dollar", 2, "S$"), "SHP": ("Saint Helena Pound", 2, "SHP"), "SLE": ("Sierra Leonean Leone", 2, "SLE"),
    "SOS": ("Somali Shilling", 2, "SOS"), "SRD": ("Surinamese Dollar", 2, "SRD"), "SSP": ("South Sudanese Pound", 2, "SSP"),
    "STN": ("Sao Tome and Principe Dobra", 2, "STN"), "SVC": ("Salvadoran Colon", 2, "SVC"), "SYP": ("Syrian Pound", 2, "SYP"),
    "SZL": ("Swazi Lilangeni", 2, "SZL"), "THB": ("Thai Baht", 2, "THB"), "TJS": ("Tajikistani Somoni", 2, "TJS"),
    "TMT": ("Turkmenistani Manat", 2, "TMT"), "TND": ("Tunisian Dinar", 3, "TND"), "TOP": ("Tongan Paanga", 2, "TOP"),
    "TRY": ("Turkish Lira", 2, "TRY"), "TTD": ("Trinidad and Tobago Dollar", 2, "TTD"), "TWD": ("New Taiwan Dollar", 2, "NT$"),
    "TZS": ("Tanzanian Shilling", 2, "TZS"), "UAH": ("Ukrainian Hryvnia", 2, "UAH"), "UGX": ("Ugandan Shilling", 0, "UGX"),
    "USD": ("US Dollar", 2, "$"), "UYU": ("Uruguayan Peso", 2, "UYU"), "UZS": ("Uzbekistani Som", 2, "UZS"),
    "VES": ("Venezuelan Bolivar", 2, "VES"), "VND": ("Vietnamese Dong", 0, "₫"), "VUV": ("Vanuatu Vatu", 0, "VUV"),
    "WST": ("Samoan Tala", 2, "WST"), "XAF": ("Central African CFA Franc", 0, "XAF"), "XCD": ("East Caribbean Dollar", 2, "XCD"),
    "XOF": ("West African CFA Franc", 0, "XOF"), "XPF": ("CFP Franc", 0, "XPF"), "YER": ("Yemeni Rial", 2, "YER"),
    "ZAR": ("South African Rand", 2, "ZAR"), "ZMW": ("Zambian Kwacha", 2, "ZMW"), "ZWL": ("Zimbabwean Dollar", 2, "ZWL"),
}

# Shown first in pickers; every other ISO code is still fully supported.
COMMON_CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SAR", "QAR", "JPY", "CNY", "SGD", "AUD", "CAD", "CHF", "NZD", "ZAR"]

# Currencies Management may pick for the display-only conversion.
MANAGEMENT_DISPLAY_CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SAR", "SGD", "AUD", "CAD", "CHF", "JPY", "CNY", "QAR", "NZD", "ZAR"]


def normalize_currency(code: str | None) -> str:
    value = (code or "").strip().upper()
    if value not in _CURRENCIES:
        raise ValueError(f"Unsupported currency code: {code!r}")
    return value


def is_supported_currency(code: str | None) -> bool:
    return (code or "").strip().upper() in _CURRENCIES


def currency_minor_units(code: str) -> int:
    return _CURRENCIES[normalize_currency(code)][1]


def list_currencies() -> list[dict]:
    common = [code for code in COMMON_CURRENCIES if code in _CURRENCIES]
    rest = sorted(code for code in _CURRENCIES if code not in common)
    return [
        {"code": code, "name": _CURRENCIES[code][0], "symbol": _CURRENCIES[code][2], "minor_units": _CURRENCIES[code][1], "common": code in COMMON_CURRENCIES}
        for code in [*common, *rest]
    ]
