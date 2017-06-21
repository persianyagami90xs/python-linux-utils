# linux-utils: Linux system administration tools for Python.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: June 21, 2017
# URL: https://linux-utils.readthedocs.io

"""
Python API for cryptsetup to control LUKS_ full disk encryption.

The functions in this module serve two distinct purposes:

**Low level Python API for cryptsetup**
 The following functions and class provide a low level Python API for the basic
 functionality of cryptsetup_:

 - :func:`create_image_file()`
 - :func:`generate_key_file()`
 - :func:`create_encrypted_filesystem()`
 - :func:`unlock_filesystem()`
 - :func:`lock_filesystem()`
 - :class:`TemporaryKeyFile()`

 This functionality make it easier for me to write test suites for Python
 projects involving full disk encryption, for example crypto-drive-manager_
 and rsync-system-backup_.

**Python implementation of cryptdisks_start and cryptdisks_stop**
 The command line programs cryptdisks_start_ and cryptdisks_stop_ are easy to
 use wrappers for cryptsetup_ that parse `/etc/crypttab`_ to find the
 information they need.

 The nice thing about `/etc/crypttab`_ is that it provides a central place to
 configure the names of encrypted filesystems, so that you can refer to a
 symbolic name instead of having to constantly repeat all of the necessary
 information (the target name, source device, key file and encryption
 options).

 A not so nice thing about cryptdisks_start_ and cryptdisks_stop_ is that these
 programs (and the whole `/etc/crypttab`_ convention) appear to be specific to
 the Debian_ ecosystem.

 The functions :func:`cryptdisks_start()` and :func:`cryptdisks_stop()` emulate
 the behavior of the command line programs when needed so that Linux
 distributions that don't offer these programs can still be supported by
 projects like crypto-drive-manager_ and rsync-system-backup_.

.. _cryptsetup: https://manpages.debian.org/cryptsetup
.. _LUKS: https://en.wikipedia.org/wiki/Linux_Unified_Key_Setup
.. _crypto-drive-manager: https://pypi.python.org/pypi/crypto-drive-manager
.. _rsync-system-backup: https://pypi.python.org/pypi/rsync-system-backup
.. _cryptdisks_start: https://manpages.debian.org/cryptdisks_start
.. _cryptdisks_stop: https://manpages.debian.org/cryptdisks_stop
.. _/etc/crypttab: https://manpages.debian.org/crypttab
.. _Debian: https://en.wikipedia.org/wiki/Debian
"""

# Standard library modules.
import logging

# External dependencies.
from executor import quote

# Modules included in our package.
from linux_utils import coerce_context, coerce_size
from linux_utils.crypttab import parse_crypttab

DEFAULT_KEY_SIZE = 2048
"""The default size (in bytes) of key files generated by :func:`generate_key_file()` (a number)."""

# Initialize a logger for this module.
logger = logging.getLogger(__name__)


def create_image_file(filename, size, context=None):
    r"""
    Create an image file filled with bytes containing zero (``\0``).

    :param filename: The pathname of the image file (a string).
    :param size: How large the image file should be (see :func:`.coerce_size()`).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~exceptions.ValueError` when `size` is invalid,
             :exc:`~executor.ExternalCommandFailed` when the command fails.
    """
    context = coerce_context(context)
    size = coerce_size(size)
    logger.debug("Creating image file of %i bytes: %s", size, filename)
    head_command = 'head --bytes=%i /dev/zero > %s'
    context.execute(head_command % (size, quote(filename)), shell=True, tty=False)


def generate_key_file(filename, size=DEFAULT_KEY_SIZE, context=None):
    """
    Generate a file with random contents that can be used as a key file.

    :param filename: The pathname of the key file (a string).
    :param size: How large the key file should be (see :func:`.coerce_size()`,
                 defaults to :data:`DEFAULT_KEY_SIZE`).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when the command fails.
    """
    context = coerce_context(context)
    size = coerce_size(size)
    logger.debug("Creating key file of %i bytes: %s", size, filename)
    context.execute(
        'dd', 'if=/dev/urandom', 'of=%s' % filename,
        'bs=%i' % size, 'count=1',
        # I'd rather use `status=none' then silent=True, however the
        # `status=none' flag isn't supported on Ubuntu 12.04 which
        # currently runs on Travis CI, so there you go :-p.
        silent=True, sudo=True,
    )
    context.execute('chown', 'root:root', filename, sudo=True)
    context.execute('chmod', '400', filename, sudo=True)


def create_encrypted_filesystem(device_file, key_file=None, context=None):
    """
    Create an encrypted LUKS filesystem.

    :param device_file: The pathname of the block special device or file (a string).
    :param key_file: The pathname of the key file used to encrypt the
                     filesystem (a string or :data:`None`).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when the command fails.

    If no `key_file` is given the operator is prompted to choose a password.
    """
    context = coerce_context(context)
    logger.debug("Creating encrypted filesystem on %s ..", device_file)
    format_command = ['cryptsetup']
    if key_file:
        format_command.append('--batch-mode')
    format_command.append('luksFormat')
    format_command.append(device_file)
    if key_file:
        format_command.append(key_file)
    context.execute(*format_command, sudo=True, tty=(key_file is None))


def unlock_filesystem(device_file, target, key_file=None, context=None):
    """
    Unlock an encrypted LUKS filesystem.

    :param device_file: The pathname of the block special device or file (a string).
    :param target: The mapped device name (a string).
    :param key_file: The pathname of the key file used to encrypt the
                     filesystem (a string or :data:`None`).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when the command fails.

    If no `key_file` is given the operator is prompted to enter a password.
    """
    context = coerce_context(context)
    logger.debug("Unlocking filesystem %s ..", device_file)
    open_command = ['cryptsetup']
    if key_file:
        open_command.append('--key-file=%s' % key_file)
    open_command.extend(['luksOpen', device_file, target])
    context.execute(*open_command, sudo=True, tty=(key_file is None))


def lock_filesystem(target, context=None):
    """
    Lock a currently unlocked LUKS filesystem.

    :param target: The mapped device name (a string).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when the command fails.
    """
    context = coerce_context(context)
    logger.debug("Locking filesystem %s ..", target)
    close_command = ['cryptsetup', 'luksClose', target]
    context.execute(*close_command, sudo=True, tty=False)


def cryptdisks_start(target, context=None):
    """
    Execute cryptdisks_start_ or emulate its functionality.

    :param target: The mapped device name (a string).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when a command fails,
             :exc:`~exceptions.ValueError` when no entry in `/etc/crypttab`_
             matches `target`.
    """
    context = coerce_context(context)
    logger.debug("Checking if `cryptdisks_start' program is installed ..")
    if context.find_program('cryptdisks_start'):
        logger.debug("Using the real `cryptdisks_start' program ..")
        context.execute('cryptdisks_start', target, sudo=True)
    else:
        logger.debug("Emulating `cryptdisks_start' functionality (program not installed) ..")
        for entry in parse_crypttab(context=context):
            if entry.target == target and 'luks' in entry.options:
                logger.debug("Matched /etc/crypttab entry: %s", entry)
                if entry.is_unlocked:
                    logger.debug("Encrypted filesystem is already unlocked, doing nothing ..")
                else:
                    unlock_filesystem(context=context,
                                      device_file=entry.source_device,
                                      key_file=entry.key_file,
                                      target=entry.target)
                break
        else:
            msg = "Encrypted filesystem not listed in /etc/crypttab! (%r)"
            raise ValueError(msg % target)


def cryptdisks_stop(target, context=None):
    """
    Execute cryptdisks_stop_ or emulate its functionality.

    :param target: The mapped device name (a string).
    :param context: An execution context created by :mod:`executor.contexts`
                    (coerced using :func:`.coerce_context()`).
    :raises: :exc:`~executor.ExternalCommandFailed` when a command fails,
             :exc:`~exceptions.ValueError` when no entry in `/etc/crypttab`_
             matches `target`.

    .. _cryptdisks_stop: https://manpages.debian.org/cryptdisks_stop
    """
    context = coerce_context(context)
    logger.debug("Checking if `cryptdisks_stop' program is installed ..")
    if context.find_program('cryptdisks_stop'):
        logger.debug("Using the real `cryptdisks_stop' program ..")
        context.execute('cryptdisks_stop', target, sudo=True)
    else:
        logger.debug("Emulating `cryptdisks_stop' functionality (program not installed) ..")
        for entry in parse_crypttab(context=context):
            if entry.target == target and 'luks' in entry.options:
                logger.debug("Matched /etc/crypttab entry: %s", entry)
                if entry.is_unlocked:
                    lock_filesystem(context=context, target=target)
                else:
                    logger.debug("Encrypted filesystem is already locked, doing nothing ..")
                break
        else:
            msg = "Encrypted filesystem not listed in /etc/crypttab! (%r)"
            raise ValueError(msg % target)


class TemporaryKeyFile(object):

    """Context manager that makes it easier to work with temporary key files."""

    def __init__(self, filename, size=DEFAULT_KEY_SIZE, context=None):
        """
        Initialize a :class:`TemporaryKeyFile` object.

        Refer to :func:`generate_key_file()`
        for details about argument handling.
        """
        self.context = coerce_context(context)
        self.filename = filename
        self.size = size

    def __enter__(self):
        """Generate the temporary key file."""
        generate_key_file(
            context=self.context,
            filename=self.filename,
            size=self.size,
        )

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        """Delete the temporary key file."""
        self.context.execute('rm', '--force', self.filename, sudo=True)
