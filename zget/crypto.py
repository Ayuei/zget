from __future__ import absolute_import, division, print_function, \
    unicode_literals
import itertools
import base64
import os
from . import utils
from .utils import _


outdated_msg = " " + _(
    "Maybe the other end is "
    "not using encryption or is running an outdated version "
    "of zget?"
)


def password_derive(key, salt):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf import pbkdf2
    from cryptography.hazmat import backends

    kdf = pbkdf2.PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        iterations=100000,
        backend=backends.default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(key))


class aes(object):
    class encrypt(object):
        def __init__(self, str_key):
            utils.logger.debug(_("Initializing AES encryptor"))

            from cryptography.hazmat import backends

            self.backend = backends.default_backend()
            self.key = None
            self.iv = None
            self.salt = None
            self.hmac_salt = None
            self.cipher = None
            self.cryptor = None
            self.str_key = str_key.encode()
            self.iv_sent = False

        def start(self):
            return b""

        def finish(self, msg):
            pass

        def __call__(self, data):
            from cryptography.hazmat.primitives import ciphers, hmac, hashes

            utils.logger.debug(
                _("Initializing AES parameters")
            )
            self.salt = os.urandom(16)
            self.hmac_salt = os.urandom(16)
            self.iv = os.urandom(16)
            self.key = password_derive(self.str_key, self.salt)
            self.hmac_key = password_derive(self.str_key, self.hmac_salt)
            del self.str_key
            self.h = hmac.HMAC(
                self.hmac_key,
                hashes.SHA256(),
                backend=self.backend
            )
            self.cipher = ciphers.Cipher(
                ciphers.algorithms.AES(self.key),
                ciphers.modes.CTR(self.iv),
                backend=self.backend,
            )
            self.cryptor = self.cipher.encryptor()

            for raw in data:
                out = self.cryptor.update(raw)

                if not self.iv_sent:
                    out = self.iv + self.salt + self.hmac_salt + out
                    self.iv_sent = True

                self.h.update(out)

                yield out

            out = self.cryptor.finalize()
            self.h.update(out)
            yield out

            utils.logger.debug(_("Sending HMAC signature"))
            signature = self.h.finalize()
            yield signature

        def size(self, x):
            return x + 80   # iv, salts and signature are 80 bytes

    class decrypt(object):
        def __init__(self, str_key):
            utils.logger.debug(_("Initializing AES decryptor"))

            from cryptography.hazmat import backends

            self.backend = backends.default_backend()
            self.key = None
            self.iv = None
            self.salt = None
            self.hmac_salt = None
            self.cipher = None
            self.cryptor = None
            self.str_key = str_key.encode()

        def start(self):
            return b""

        def finish(self, msg):
            pass

        def __call__(self, data):
            from cryptography.hazmat.primitives import ciphers, hmac, hashes
            import cryptography.exceptions

            # ensure minimum chunksize of 32 so we can easily read signature
            # iterate pairwise to detect last chunk and verify HMAC
            for enc, nextenc in utils.pairwise(utils.minimum_chunksize(data)):
                if self.iv is None:
                    utils.logger.debug(_("Received AES parameters"))
                    self.iv = enc[:16]
                    self.salt = enc[16:32]
                    self.hmac_salt = enc[32:48]
                    self.key = password_derive(self.str_key, self.salt)
                    self.hmac_key = password_derive(
                        self.str_key, self.hmac_salt
                    )
                    del self.str_key
                    self.h = hmac.HMAC(
                        self.hmac_key,
                        hashes.SHA256(),
                        backend=self.backend
                    )
                    self.cipher = ciphers.Cipher(
                        ciphers.algorithms.AES(self.key),
                        ciphers.modes.CTR(self.iv),
                        backend=self.backend,
                    )
                    self.cryptor = self.cipher.decryptor()
                    self.h.update(self.iv + self.salt + self.hmac_salt)

                    enc = enc[48:]

                if nextenc is None:
                    signature = enc[-32:]
                    enc = enc[:-32]
                    utils.logger.debug(_("Received HMAC signature"))
                    self.h.update(enc)
                    try:
                        self.h.verify(signature)
                        utils.logger.debug(_("HMAC verification OK"))
                    except cryptography.exceptions.InvalidSignature:
                        raise RuntimeError(
                            _("File decryption and verification failed. Did "
                              "you supply the correct password?")
                            )
                else:
                    self.h.update(enc)

                yield self.cryptor.update(enc)

            yield self.cryptor.finalize()

        def size(self, x):
            return x - 80   # iv, salts and signature are 80 bytes


class aes_spake(object):
    class encrypt(aes.encrypt):
        def __init__(self, str_key):
            super(aes_spake.encrypt, self).__init__(str_key)
            utils.logger.debug(_("Initializing AES SPAKE2 encryptor"))
            from spake2 import SPAKE2_B

            self.exchange = SPAKE2_B(str_key.encode())
            self.str_key = None

        def start(self):
            return self.exchange.start()

        def finish(self, msg):
            from spake2 import SPAKEError

            try:
                self.str_key = self.exchange.finish(msg)
                utils.logger.debug(
                    _("SPAKE2 Key Exchange finished")
                )
            except SPAKEError:
                raise ValueError(_("The key exchange failed.") + outdated_msg)

        def __call__(self, data):
            if self.str_key is None:
                raise RuntimeError(
                    _("Password key exchange did not finish before starting "
                      "the transfer.") + outdated_msg
                )

            for x in super(aes_spake.encrypt, self).__call__(data):
                yield x

    class decrypt(aes.decrypt):
        def __init__(self, str_key):
            super(aes_spake.decrypt, self).__init__(str_key)
            utils.logger.debug(_("Initializing AES SPAKE2 decryptor"))
            from spake2 import SPAKE2_A

            self.exchange = SPAKE2_A(str_key.encode())
            self.str_key = None

        def start(self):
            return self.exchange.start()

        def finish(self, msg):
            from spake2 import SPAKEError

            try:
                self.str_key = self.exchange.finish(msg)
                utils.logger.debug(
                    _("SPAKE2 Key Exchange finished")
                )
            except SPAKEError:
                raise ValueError(
                    _("The key exchange failed.") + outdated_msg
                )

        def __call__(self, data):
            if self.str_key is None:
                raise RuntimeError(
                    _("Password key exchange did not finish before starting "
                      "the transfer.") + outdated_msg
                )

            for x in super(aes_spake.decrypt, self).__call__(data):
                yield x


class bypass(object):
    class encrypt(object):
        def __init__(self, key=""):
            utils.logger.debug(_("Initializing bypass cryptor"))

        def start(self):
            return b""

        def finish(self, msg):
            pass

        def __call__(self, data):
            for chunk in data:
                yield chunk

        def size(self, x):
            return x

    decrypt = encrypt
