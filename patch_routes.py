with open("app/routes/product_routes.py", "r") as f:
    content = f.read()

old_code = """@router.get("/catalog")
def get_catalog(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    return db.query(GlobalProduct).filter(
        or_(
            GlobalProduct.is_verified == True,
            GlobalProduct.created_by_shop_id == current_shop.id
        )
    ).all()"""

new_code = """@router.get("/catalog")
def get_catalog(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    rows = (
        db.query(GlobalProductVariant, GlobalProduct.name)
        .join(GlobalProduct, GlobalProductVariant.product_id == GlobalProduct.id)
        .filter(
            or_(
                GlobalProductVariant.is_verified == True,
                GlobalProductVariant.created_by_shop_id == current_shop.id
            )
        )
        .all()
    )
    
    return [
        {
            "id": v.product_id,
            "name": name,
            "variant_name": v.variant_name,
            "brand": v.brand,
            "is_verified": v.is_verified
        }
        for v, name in rows
    ]"""

content = content.replace(old_code, new_code)

with open("app/routes/product_routes.py", "w") as f:
    f.write(content)
