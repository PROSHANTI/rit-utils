import logging

logger = logging.getLogger(__name__)


class EmailTemplate:
    def render(self) -> str:
        """Возвращает шаблон email с правильным форматированием"""
        logger.debug("Подготовка шаблона письма")
        return "".join(
            (
                "Добрый вечер!\n\n",
                "{body_cashless}",
                "{body_card}",
                "{body_qr}",
                "{body_cash}",
                "\n",
                "С уважением, Анастасия\n",
                "Администратор\n",
                "ReInTa Clinic\n",
                'ООО "ФЭМИЛИС"\n',
                "Москва, Новолесной переулок 5\n",
                "тел.: +7(499)110-37-77",
            )
        )


get_email_template = EmailTemplate().render
