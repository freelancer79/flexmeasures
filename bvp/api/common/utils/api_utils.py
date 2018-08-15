import copy
from typing import List, Union
from functools import wraps
from json import loads as parse_json, JSONDecodeError

from bvp.data import db
from bvp.data.models.assets import Asset


def check_access(service_listing, service_name):
    """
    For a given USEF service name (API endpoint) in a service listing,
    return the list of USEF roles that are allowed to access the service.
    """
    return next(
        service["access"]
        for service in service_listing["services"]
        if service["name"] == service_name
    )


def contains_empty_items(groups: List[List[str]]):
    """
    Return True if any of the items in the groups is empty.
    """
    for group in groups:
        for item in group:
            if item == "" or item is None:
                return True
    return False


def parse_as_list(connection: Union[List[str], str]) -> List[str]:
    """
    Return a list of connections, even if it's just one connection
    """
    if isinstance(connection, str):
        connections = [connection]
    elif isinstance(connection, list):  # key should have been plural
        connections = connection
    else:
        connections = []
    return connections


def get_form_from_request(_request) -> Union[dict, None]:
    if _request.method == "GET":
        d = _request.args.to_dict(
            flat=False
        )  # From MultiDict, obtain all values with the same key as a list
        parsed_d = {}
        for k, v_list in d.items():
            parsed_v_list = []
            for v in v_list:
                try:
                    parsed_v = parse_json(v)
                except JSONDecodeError:
                    parsed_v = v
                if isinstance(parsed_v, list):
                    parsed_v_list.extend(parsed_v)
                else:
                    parsed_v_list.append(v)
            if len(parsed_v_list) == 1:  # Flatten single-value lists
                parsed_d[k] = parsed_v_list[0]
            else:
                parsed_d[k] = parsed_v_list
        return parsed_d
    elif _request.method == "POST":
        return _request.get_json(force=True)
    else:
        return None


def append_doc_of(fun):
    def decorator(f):
        if f.__doc__:
            f.__doc__ += fun.__doc__
        else:
            f.__doc__ = fun.__doc__
        return f

    return decorator


def groups_to_dict(
    connection_groups: List[List[str]], value_groups: List[List[str]]
) -> dict:
    """Put the connections and values in a dictionary and simplify if groups have identical values and/or if there is
    only one group.

    Examples:

        >> connection_groups = [[1]]
        >> value_groups = [[300, 300, 300]]
        >> response_dict = groups_to_dict(connection_groups, value_groups)
        >> print(response_dict)
        <<  {
                "connection": 1,
                "values": [300, 300, 300]
            }

        >> connection_groups = [[1], [2]]
        >> value_groups = [[300, 300, 300], [300, 300, 300]]
        >> response_dict = groups_to_dict(connection_groups, value_groups)
        >> print(response_dict)
        <<  {
                "connections": [1, 2],
                "values": [300, 300, 300]
            }

        >> connection_groups = [[1], [2]]
        >> value_groups = [[300, 300, 300], [400, 400, 400]]
        >> response_dict = groups_to_dict(connection_groups, value_groups)
        >> print(response_dict)
        <<  {
                "groups": [
                    {
                        "connection": 1,
                        "values": [300, 300, 300]
                    },
                    {
                        "connection": 2,
                        "values": [400, 400, 400]
                    }
                ]
            }
    """

    # Simplify groups that have identical values
    value_groups, connection_groups = unique_ever_seen(value_groups, connection_groups)

    # Simplify if there is only one group
    if len(value_groups) == len(connection_groups) == 1:
        if len(connection_groups[0]) == 1:
            return {"connection": connection_groups[0][0], "values": value_groups[0]}
        else:
            return {"connections": connection_groups[0], "values": value_groups[0]}
    else:
        d = {"groups": []}
        for connection_group, value_group in zip(connection_groups, value_groups):
            if len(connection_group) == 1:
                d["groups"].append(
                    {"connection": connection_group[0], "values": value_group}
                )
            else:
                d["groups"].append(
                    {"connections": connection_group, "values": value_group}
                )
        return d


def unique_ever_seen(iterable, selector):
    """
    Return unique iterable elements with corresponding lists of selector elements, preserving order.
    """
    u = []
    s = []
    for iterable_element, selector_element in zip(iterable, selector):
        if iterable_element not in u:
            u.append(iterable_element)
            s.append(selector_element)
        else:
            us = s[u.index(iterable_element)]
            if not isinstance(us, list):
                us = [us]
            us.append(selector_element)
            s[u.index(iterable_element)] = us
    return u, s


def message_replace_name_with_ea(message_with_connections_as_asset_names: dict) -> dict:
    """For each connection in the message specified by a name, replace that name with the correct entity address."""
    message_with_connections_as_eas = copy.deepcopy(
        message_with_connections_as_asset_names
    )
    if "connection" in message_with_connections_as_asset_names:
        message_with_connections_as_eas["connection"] = asset_replace_name_with_id(
            parse_as_list(message_with_connections_as_eas["connection"])
        )
    elif "connections" in message_with_connections_as_asset_names:
        message_with_connections_as_eas["connections"] = asset_replace_name_with_id(
            parse_as_list(message_with_connections_as_eas["connections"])
        )
    elif "groups" in message_with_connections_as_asset_names:
        for i, group in enumerate(message_with_connections_as_asset_names["groups"]):
            if "connection" in group:
                message_with_connections_as_eas["groups"][i][
                    "connection"
                ] = asset_replace_name_with_id(parse_as_list(group["connection"]))
            elif "connections" in group:
                message_with_connections_as_eas["groups"][i][
                    "connections"
                ] = asset_replace_name_with_id(parse_as_list(group["connections"]))
    return message_with_connections_as_eas


def asset_replace_name_with_id(connections_as_name: List[str]) -> List[str]:
    """Look up the owner and id given the asset name and construct a type 1 USEF entity address."""
    connections_as_ea = []
    for asset_name in connections_as_name:
        asset = Asset.query.filter(Asset.name == asset_name).one_or_none()
        connections_as_ea.append(asset.entity_address)
    return connections_as_ea


def zip_dic(*dicts):
    for i in set(dicts[0]).intersection(*dicts[1:]):
        yield (i,) + tuple(d[i] for d in dicts)


def save_to_database(objects: List[db.Model], overwrite: bool = False):
    """Utility function to save to database, either efficiently with a bulk save, or inefficiently with a merge save."""
    if not overwrite:
        db.session.bulk_save_objects(objects)
    else:
        for o in objects:
            db.session.merge(o)


class BaseMessage:
    """Set a base message to which extra info can be added by calling the wrapped function with additional string
    arguments. This is a decorator implemented as a class."""

    def __init__(self, base_message=""):
        self.base_message = base_message

    def __call__(self, func):
        @wraps(func)
        def my_logic(*args, **kwargs):
            message = self.base_message
            if args:
                for a in args:
                    message += " %s" % a
            return func(message)

        return my_logic
