"""Tests para los parsers de logs.

Verifica que cada parser convierta correctamente logs crudos
al formato normalizado de SentinelPy.
"""


class TestSyslogParser:
    """Pruebas para el parser de syslog RFC 3164."""

    def setup_method(self):
        from app.services.parser import SyslogParser

        self.parser = SyslogParser()

    def test_parse_rfc3164_completo(self):
        """Parsea un mensaje RFC 3164 completo con PID."""
        raw = "<30>Oct  9 22:33:20 myhost sshd[12345]: Failed password for root from 192.168.1.100 port 22 ssh2"
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["source"] == "myhost"
        assert resultado["collector_type"] == "syslog"
        assert resultado["event_type"] == "auth_failure"
        assert resultado["severity"] == "info"  # PRI=30 → severity=6 → info
        assert resultado["process_name"] == "sshd"
        assert "root" in resultado["description"]
        assert resultado["source_ip"] == "192.168.1.100"
        assert resultado["collector_type"] == "syslog"

    def test_parse_rfc3164_sin_pid(self):
        """Parsea un mensaje RFC 3164 sin PID."""
        raw = "<14>Oct  9 22:33:20 myhost sudo: pam_unix(sudo:auth): authentication failure"
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["process_name"] == "sudo"
        assert resultado["event_type"] == "privilege_escalation"
        assert resultado["severity"] == "info"

    def test_parse_rfc3164_auth_success(self):
        """Detecta autenticación exitosa SSH."""
        raw = "<30>Oct 10 08:15:30 server sshd[9999]: Accepted password for admin from 10.0.0.1 port 22 ssh2"
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["event_type"] == "auth_success"
        assert resultado["source_ip"] == "10.0.0.1"

    def test_parse_linea_vacia(self):
        """Devuelve None para línea vacía."""
        assert self.parser.parse("") is None
        assert self.parser.parse("   ") is None

    def test_parse_formato_invalido(self):
        """Devuelve None para formato no reconocido."""
        assert self.parser.parse("esto no es un syslog") is None


class TestJSONParser:
    """Pruebas para el parser de logs en formato JSON."""

    def setup_method(self):
        from app.services.parser import JSONParser

        self.parser = JSONParser()

    def test_parse_json_completo(self):
        """Parsea un JSON con todos los campos."""
        raw = '{"host":"web-01","type":"http_request","level":"error","message":"500 error en /api/users","src_ip":"192.168.1.50","user":"admin","process":"nginx"}'
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["source"] == "web-01"
        assert resultado["event_type"] == "http_request"
        assert resultado["severity"] == "high"  # error → high
        assert "500 error" in resultado["description"]
        assert resultado["source_ip"] == "192.168.1.50"
        assert resultado["user_name"] == "admin"
        assert resultado["process_name"] == "nginx"
        assert resultado["collector_type"] == "json"

    def test_parse_json_minimo(self):
        """Parsea un JSON con solo campos obligatorios."""
        raw = '{"message":"test"}'
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["source"] is None
        assert resultado["event_type"] == "json_event"
        assert resultado["severity"] == "info"
        assert resultado["collector_type"] == "json"

    def test_parse_json_linea_vacia(self):
        """Devuelve None para línea vacía."""
        assert self.parser.parse("") is None

    def test_parse_json_invalido(self):
        """Devuelve None para JSON mal formado."""
        assert self.parser.parse("{esto no es json}") is None

    def test_normalizar_severidad(self):
        """Normaliza distintos formatos de severidad."""
        from app.services.parser import JSONParser

        parser_local = JSONParser()

        # Probar distintos inputs
        assert parser_local._normalizar_severidad("error") == "high"
        assert parser_local._normalizar_severidad("ERROR") == "high"
        assert parser_local._normalizar_severidad("warn") == "medium"
        assert parser_local._normalizar_severidad("critical") == "critical"
        assert parser_local._normalizar_severidad("debug") == "info"
        assert parser_local._normalizar_severidad("") == "info"
        assert parser_local._normalizar_severidad(None) == "info"

    def test_mapeo_campos_json(self):
        """Verifica que el mapeo de campos alternativos funcione."""
        # Usar 'hostname' en vez de 'source', 'message' en vez de 'description'
        raw = '{"hostname":"db-01","level":"crit","message":"conexion perdida","src":"10.0.0.5","user":"root","app":"postgres"}'
        resultado = self.parser.parse(raw)

        assert resultado is not None
        assert resultado["source"] == "db-01"
        assert resultado["severity"] == "critical"
        assert resultado["description"] == "conexion perdida"
        assert resultado["source_ip"] == "10.0.0.5"
        assert resultado["user_name"] == "root"
        assert resultado["process_name"] == "postgres"
