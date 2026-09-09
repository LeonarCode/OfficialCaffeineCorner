import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


class UnverifiedSSLEmailBackend(SMTPBackend):
    def open(self):
        if self.connection:
            return False
        connection_params = {}
        if self.timeout is not None:
            connection_params['timeout'] = self.timeout
        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)

            if not self.use_ssl and self.use_tls:
                context = ssl._create_unverified_context()
                self.connection.starttls(context=context)

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise
            return False