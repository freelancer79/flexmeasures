import isodate
from typing import List, Tuple, Union
from datetime import datetime as datetime_type, timedelta

from flask import request
from flask_json import as_json
from flask_security import current_user
from sqlalchemy.exc import IntegrityError

from bvp.data.config import db
from bvp.data.models.assets import Asset, Power
from bvp.data.models.data_sources import DataSource
from bvp.api.common.responses import (
    already_received_and_successfully_processed,
    invalid_domain,
    invalid_role,
    power_value_too_big,
    power_value_too_small,
    unrecognized_connection_group,
    request_processed,
)
from bvp.data.services.resources import get_assets
from bvp.api.common.utils.api_utils import (
    message_replace_name_with_ea,
    groups_to_dict,
    save_to_database,
    make_forecasting_jobs,
)
from bvp.api.common.utils.validators import (
    type_accepted,
    units_accepted,
    assets_required,
    optional_sources_accepted,
    resolutions_accepted,
    optional_resolutions_accepted,
    optional_horizon_accepted,
    period_required,
    values_required,
    validate_entity_address,
)


@type_accepted("GetMeterDataRequest")
@units_accepted("MW")
@optional_resolutions_accepted("PT15M")
@assets_required("connection")
@optional_sources_accepted(preferred_source="MDC")
@optional_horizon_accepted(ex_post=True)
@period_required
@as_json
def get_meter_data_response(
    unit,
    resolution,
    generic_asset_name_groups,
    horizon,
    rolling,
    start,
    duration,
    preferred_source_ids,
    fallback_source_ids,
) -> Tuple[dict, int]:
    """
    Read out the power values for each asset.
    The response message has a different structure depending on:
        1) the number of connections for which meter data is requested, and
        2) whether the time window in the request maps an integer number of time slots for the meter data
    In all cases, the API defaults to use shorthand for univariate timeseries data,
    in which the data resolution can be derived by dividing the duration of the time window over the number of values.
    """

    # Any meter data observed at most <horizon> after the fact and not before the fact
    horizon_window = (horizon, timedelta(hours=0))

    return collect_connection_and_value_groups(
        unit,
        resolution,
        horizon_window,
        start,
        duration,
        generic_asset_name_groups,
        preferred_source_ids,
        fallback_source_ids,
        rolling=rolling,
    )


@type_accepted("PostMeterDataRequest")
@units_accepted("MW")
@assets_required("connection")
@values_required
@optional_horizon_accepted(ex_post=True)
@period_required
@resolutions_accepted(timedelta(minutes=15))
@as_json
def post_meter_data_response(
    unit, generic_asset_name_groups, value_groups, horizon, rolling, start, duration
) -> Union[dict, Tuple[dict, int]]:
    """
    Store the new power values for each asset.
    """

    return create_connection_and_value_groups(
        unit, generic_asset_name_groups, value_groups, horizon, rolling, start, duration
    )


@as_json
def get_service_response(service_listing) -> Union[dict, Tuple[dict, int]]:
    """
    Lists the available services for the public endpoint version,
    either all of them or only those that apply to the requested access role.
    """
    requested_access_role = request.args.get("access")

    response = {"version": service_listing["version"]}
    if requested_access_role:
        accessible_services = []
        for service in service_listing["services"]:
            if requested_access_role in service["access"]:
                accessible_services.append(service)
        response["services"] = accessible_services
        if not accessible_services:
            return invalid_role(requested_access_role)
    else:
        response["services"] = service_listing["services"]
    d, s = request_processed()
    return dict(**response, **d), s


def collect_connection_and_value_groups(
    unit: str,
    resolution: str,
    horizon_window: Tuple[Union[None, timedelta], Union[None, timedelta]],
    start: datetime_type,
    duration: timedelta,
    connection_groups: List[List[str]],
    preferred_source_ids: {
        Union[int, List[int]]
    } = None,  # None is interpreted as all sources
    fallback_source_ids: Union[
        int, List[int]
    ] = -1,  # An id = -1 is interpreted as no sources
    rolling: bool = False,
) -> Tuple[dict, int]:
    from flask import current_app

    current_app.logger.info("GETTING")

    from flask import current_app

    user_assets = get_assets()
    if not user_assets:
        current_app.logger.info("User doesn't seem to have any assets")
    user_asset_ids = [asset.id for asset in user_assets]

    end = start + duration
    value_groups = []
    new_connection_groups = []  # Each connection in the old connection groups will be interpreted as a separate group
    for connections in connection_groups:

        # Get the asset names
        asset_names = []
        for connection in connections:

            # Parse the entity address
            connection = validate_entity_address(connection, entity_type="connection")
            if connection is None:
                current_app.logger.warn(
                    "Cannot parse this connection's entity address: %s" % connection
                )
                return invalid_domain()
            asset_id = connection["asset_id"]

            # Look for the Asset object
            if asset_id in user_asset_ids:
                asset = Asset.query.filter(Asset.id == asset_id).one_or_none()
            else:
                current_app.logger.warn("Cannot identify connection %s" % connection)
                return unrecognized_connection_group()
            asset_names.append(asset.name)

        # Get the power values
        ts_values = Power.collect(
            generic_asset_names=asset_names,
            query_window=(start, end),
            resolution=resolution,
            horizon_window=horizon_window,
            rolling=rolling,
            preferred_source_ids=preferred_source_ids,
            fallback_source_ids=fallback_source_ids,
            sum_multiple=False,
        )
        # Todo: parse time window of ts_values, which will be different for requests that are not of the form:
        # - start is a timestamp on the hour or a multiple of 15 minutes thereafter
        # - duration is a multiple of 15 minutes
        for k, v in ts_values.items():
            value_groups.append(
                [x * -1 for x in v.y.tolist()]
            )  # Reverse sign of values (from BVP specs to USEF specs)
            new_connection_groups.append(k)

    response = groups_to_dict(new_connection_groups, value_groups)
    response = message_replace_name_with_ea(response)
    response["start"] = isodate.datetime_isoformat(start)
    response["duration"] = isodate.duration_isoformat(duration)
    response["unit"] = unit  # TODO: convert to requested unit

    d, s = request_processed()
    return dict(**response, **d), s


def create_connection_and_value_groups(  # noqa: C901
    unit, generic_asset_name_groups, value_groups, horizon, rolling, start, duration
):
    from flask import current_app

    current_app.logger.info("POSTING POWER DATA")
    data_source = DataSource.query.filter(DataSource.user == current_user).one_or_none()
    user_assets = get_assets()
    if not user_assets:
        current_app.logger.info("User doesn't seem to have any assets")
    user_asset_ids = [asset.id for asset in user_assets]
    power_measurements = []
    forecasting_jobs = []
    for connection_group, value_group in zip(generic_asset_name_groups, value_groups):
        for connection in connection_group:

            # Parse the entity address
            connection = validate_entity_address(connection, entity_type="connection")
            if connection is None:
                current_app.logger.warn(
                    "Cannot parse this connection's entity address: %s" % connection
                )
                return invalid_domain()
            asset_id = connection["asset_id"]

            # Look for the Asset object
            if asset_id in user_asset_ids:
                asset = Asset.query.filter(Asset.id == asset_id).one_or_none()
            else:
                current_app.logger.warn("Cannot identify connection %s" % connection)
                return unrecognized_connection_group()

            # Validate the sign of the values (following USEF specs with positive consumption and negative production)
            if asset.is_pure_consumer and any(v < 0 for v in value_group):
                extra_info = (
                    "Connection %s is registered as a pure consumer and can only receive non-negative values."
                    % asset.entity_address
                )
                return power_value_too_small(extra_info)
            elif asset.is_pure_producer and any(v > 0 for v in value_group):
                extra_info = (
                    "Connection %s is registered as a pure producer and can only receive non-positive values."
                    % asset.entity_address
                )
                return power_value_too_big(extra_info)

            # Create new Power objects
            end = start
            for j, value in enumerate(value_group):
                dt = start + j * duration / len(value_group)
                if rolling:
                    h = horizon
                else:  # Deduct the difference in end times of the individual timeslot and the timeseries duration
                    h = horizon - (
                        (start + duration) - (dt + duration / len(value_group))
                    )
                p = Power(
                    datetime=dt,
                    value=value
                    * -1,  # Reverse sign for BVP specs with positive production and negative consumption
                    horizon=h,
                    asset_id=asset.id,
                    data_source_id=data_source.id,
                )
                power_measurements.append(p)
                end = dt

            if end > start:
                forecasting_jobs.extend(
                    make_forecasting_jobs("Power", asset_id, start, end)
                )

    current_app.logger.info("SAVING TO DB...")
    try:
        save_to_database(power_measurements)
        save_to_database(forecasting_jobs)
        db.session.commit()
        return request_processed()
    except IntegrityError as e:
        current_app.logger.warn(e)
        db.session.rollback()

        # Allow meter data to be replaced only in play mode
        if current_app.config.get("BVP_MODE", "") == "play":
            save_to_database(power_measurements, overwrite=True)
            save_to_database(forecasting_jobs, overwrite=True)
            db.session.commit()
            return request_processed()
        else:
            return already_received_and_successfully_processed()
