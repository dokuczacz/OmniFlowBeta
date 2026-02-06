from list_blobs.service import list_blobs_core


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in ("1", "true", "yes", "y", "on")
    return bool(value)


def list_blobs(args, user_id):
    prefix = str(args.get("prefix") or "").strip()
    include_meta = _coerce_bool(args.get("include_meta"))
    return list_blobs_core(
        user_id=user_id,
        prefix=prefix,
        include_meta=include_meta,
        raise_on_error=False,
    )
