from typing import List, Tuple, Union
import inflect

from bvp.api.common.utils.api_utils import BaseMessage

p = inflect.engine()


@BaseMessage("Some of the data has already been received and successfully processed.")
def already_received_and_successfully_processed(message: str) -> Tuple[dict, int]:
    return (
        dict(
            results="Rejected",
            status="ALREADY_RECEIVED_AND_SUCCESSFULLY_PROCESSED",
            message=message,
        ),
        400,
    )


@BaseMessage(
    "Connections, sensors and markets should be identified using the EA1 addressing scheme recommended by USEF. "
    "For example:"
    " 'ea1.2018-06.com.a1-bvp:<owner-id>:<asset-id>'"
    " 'ea1.2018-06.com.a1-bvp:temperature:<latitude>:<longitude>'"
    " 'ea1.2018-06.com.a1-bvp:<market_name>'"
)
def invalid_domain(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="INVALID_DOMAIN", message=message), 400)


@BaseMessage("The prognosis horizon in your request could not be parsed.")
def invalid_horizon(message: str) -> Tuple[dict, int]:
    return dict(result="Rejected", status="INVALID_HORIZON", message=message), 400


@BaseMessage("A time period in your request doesn't seem right.")
def invalid_period(message: str) -> Tuple[dict, int]:
    return dict(result="Rejected", status="INVALID_PERIOD", message=message), 400


@BaseMessage(
    "Start time should be on the hour or a multiple of 15 minutes thereafter, "
    "duration should be some multiple N of 15 minutes, and "
    "the number of values should be some factor of N."
)
def invalid_ptu_duration(message: str) -> Tuple[dict, int]:
    return (
        dict(result="Rejected", status="INVALID_PTU_DURATION", message=message),
        400,
    )


@BaseMessage("Only a 15 minute resolution is currently supported.")
def invalid_resolution(message: str) -> Tuple[dict, int]:
    return dict(result="Rejected", status="INVALID_RESOLUTION", message=message), 400


def invalid_method(request_method) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="INVALID_METHOD",
            message="Request method %s not supported." % request_method,
        ),
        405,
    )


def invalid_role(requested_access_role: str) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="INVALID_ROLE",
            message="No known services for specified role %s." % requested_access_role,
        ),
        400,
    )


def invalid_sender(
    user_role_names: Union[str, List[str]], *allowed_role_names: str
) -> Tuple[dict, int]:
    if isinstance(user_role_names, str):
        user_role_names = [user_role_names]
    if not user_role_names:
        user_roles_str = "have no role"
    else:
        user_role_names = [p.a(role_name) for role_name in user_role_names]
        user_roles_str = "are %s" % p.join(user_role_names)
    allowed_role_names = [pluralize(role_name) for role_name in allowed_role_names]
    allowed_role_names = p.join(allowed_role_names)
    return (
        dict(
            result="Rejected",
            status="INVALID_SENDER",
            message="You don't have the right role to access this service. "
            "You %s while this service is reserved for %s."
            % (user_roles_str, allowed_role_names),
        ),
        403,
    )


@BaseMessage("Start time should explicitly state a timezone.")
def invalid_timezone(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="INVALID_TIMEZONE", message=message), 400)


def invalid_unit(*units) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="INVALID_UNIT",
            message="Data should be given in %s." % p.join(*units, conj="or"),
        ),
        400,
    )


def invalid_message_type(message_type: str) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="INVALID_MESSAGE_TYPE",
            message="Request message should specify type '%s'." % message_type,
        ),
        400,
    )


@BaseMessage("Request message should include 'backup'.")
def no_backup(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="NO_BACKUP", message=message), 400)


@BaseMessage("Request message should include 'type'.")
def no_message_type(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="NO_MESSAGE_TYPE", message=message), 400)


@BaseMessage("One or more power values are too big.")
def power_value_too_big(message: str) -> Tuple[dict, int]:
    return dict(result="Rejected", status="POWER_VALUE_TOO_BIG", message=message), 400


@BaseMessage("One or more power values are too small.")
def power_value_too_small(message: str) -> Tuple[dict, int]:
    return (
        dict(result="Rejected", status="POWER_VALUE_TOO_SMALL", message=message),
        400,
    )


@BaseMessage("Missing values.")
def ptus_incomplete(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="PTUS_INCOMPLETE", message=message), 400)


@BaseMessage("The requested backup is not known.")
def unrecognized_backup(message: str) -> Tuple[dict, int]:
    return (dict(result="Rejected", status="UNRECOGNIZED_BACKUP", message=message), 400)


@BaseMessage("One or more connections in your request were not found in your account.")
def unrecognized_connection_group(message: str) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected", status="UNRECOGNIZED_CONNECTION_GROUP", message=message
        ),
        400,
    )


def unrecognized_market(requested_market) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="UNRECOGNIZED_MARKET",
            message="The requested market named %s is not known." % requested_market,
        ),
        400,
    )


def unrecognized_sensor(lat, lng) -> Tuple[dict, int]:
    return (
        dict(
            result="Rejected",
            status="UNRECOGNIZED_SENSOR",
            message="No sensor is known at this location. The nearest sensor is at latitude %s and longitude %s"
            % (lat, lng),
        ),
        400,
    )


@BaseMessage("Request has been processed.")
def request_processed(message: str) -> Tuple[dict, int]:
    return dict(status="PROCESSED", message=message), 200


def pluralize(usef_role_name):
    """Adding a trailing 's' works well for USEF roles."""
    return "%ss" % usef_role_name
