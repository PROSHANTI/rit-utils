def get_email_template():
    """Возвращает шаблон email с правильным форматированием"""
    return (
        'Добрый вечер!\n'
        '\n'
        '{body_cashless}'
        '{body_card}'
        '{body_qr}'
        '{body_cash}'
        '\n'
        'С уважением'
    )