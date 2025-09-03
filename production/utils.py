def apply_client_scope(qs, request, key="client_scope_id"):
    """
    Restrict queryset to the client currently selected in session.
    - "all": no filter
    - "shared": filter where client is null
    - numeric id: filter by client_id
    """
    cid = request.session.get(key)

    if not cid or cid == "all":
        return qs

    if cid == "shared":
        return qs.filter(client__isnull=True)

    try:
        return qs.filter(client_id=int(cid))
    except (TypeError, ValueError):
        return qs