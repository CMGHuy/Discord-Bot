from swingbot import config


def test_etoro_credentials_declared_blank_and_sensitive():
    keys = {f.key: f for f in config.FIELDS}
    for k in ("ETORO_USER_KEY", "ETORO_API_KEY"):
        assert keys[k].section == "eToro Paper Trading"
        assert keys[k].default == "" and keys[k].sensitive is True
