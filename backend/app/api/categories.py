import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.category import Category
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryReorderRequest,
    CategoryUpdate,
)
from app.services.default_categories import DEFAULT_CATEGORIES

router = APIRouter()


def _get_owned_category(category_id: uuid.UUID, user: CurrentUser, db: Session) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.user_id != uuid.UUID(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


def _get_siblings(db: Session, user_id: uuid.UUID, parent_id: uuid.UUID | None) -> list[Category]:
    return list(
        db.scalars(
            select(Category).where(Category.user_id == user_id, Category.parent_id == parent_id)
        )
    )


def _seed_defaults(user_id: uuid.UUID, db: Session) -> list[Category]:
    """Populates a brand-new user's categories from DEFAULT_CATEGORIES. Seeded
    rows are ordinary rows afterward (is_default is informational only) -- the
    user can rename/delete them like anything else they create."""
    created: list[Category] = []
    for order, top in enumerate(DEFAULT_CATEGORIES):
        parent = Category(
            id=uuid.uuid4(),
            user_id=user_id,
            parent_id=None,
            name=top["name"],
            is_default=True,
            sort_order=order,
        )
        db.add(parent)
        created.append(parent)
        for sub_order, sub_name in enumerate(top["subcategories"]):
            child = Category(
                id=uuid.uuid4(),
                user_id=user_id,
                parent_id=parent.id,
                name=sub_name,
                is_default=True,
                sort_order=sub_order,
            )
            db.add(child)
            created.append(child)
    db.commit()
    return created


def _to_read(category: Category, subcategories: list[CategoryRead] | None) -> CategoryRead:
    return CategoryRead(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        is_default=category.is_default,
        sort_order=category.sort_order,
        subcategories=subcategories,
    )


def _to_tree(categories: list[Category]) -> list[CategoryRead]:
    by_parent: dict[uuid.UUID | None, list[Category]] = {}
    for c in categories:
        by_parent.setdefault(c.parent_id, []).append(c)
    for siblings in by_parent.values():
        siblings.sort(key=lambda c: c.sort_order)

    return [
        _to_read(
            top,
            subcategories=[_to_read(sub, None) for sub in by_parent.get(top.id, [])],
        )
        for top in by_parent.get(None, [])
    ]


@router.get("/api/categories", response_model=list[CategoryRead])
def list_categories(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CategoryRead]:
    user_id = uuid.UUID(user.id)
    categories = list(db.scalars(select(Category).where(Category.user_id == user_id)))
    if not categories:
        categories = _seed_defaults(user_id, db)
    return _to_tree(categories)


@router.post("/api/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryRead:
    user_id = uuid.UUID(user.id)

    if payload.parent_id is not None:
        parent = _get_owned_category(payload.parent_id, user, db)
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subcategories cannot have their own subcategories",
            )

    siblings = _get_siblings(db, user_id, payload.parent_id)
    if any(s.name.lower() == payload.name.lower() for s in siblings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A category with this name already exists"
        )

    category = Category(
        id=uuid.uuid4(),
        user_id=user_id,
        parent_id=payload.parent_id,
        name=payload.name,
        is_default=False,
        sort_order=len(siblings),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return _to_read(category, subcategories=[] if payload.parent_id is None else None)


@router.patch("/api/categories/reorder", response_model=list[CategoryRead])
def reorder_categories(
    payload: CategoryReorderRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CategoryRead]:
    user_id = uuid.UUID(user.id)
    siblings = _get_siblings(db, user_id, payload.parent_id)
    siblings_by_id = {s.id: s for s in siblings}
    if set(payload.ordered_ids) != set(siblings_by_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ordered_ids must exactly match the category's current siblings",
        )

    for index, category_id in enumerate(payload.ordered_ids):
        siblings_by_id[category_id].sort_order = index
    db.commit()

    categories = list(db.scalars(select(Category).where(Category.user_id == user_id)))
    return _to_tree(categories)


@router.patch("/api/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategoryRead:
    category = _get_owned_category(category_id, user, db)
    siblings = _get_siblings(db, uuid.UUID(user.id), category.parent_id)
    if any(s.name.lower() == payload.name.lower() and s.id != category.id for s in siblings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A category with this name already exists"
        )

    category.name = payload.name
    db.commit()
    db.refresh(category)
    return _to_read(category, subcategories=None)


@router.delete("/api/categories/{category_id}")
def delete_category(
    category_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, uuid.UUID]:
    category = _get_owned_category(category_id, user, db)
    db.delete(category)
    db.commit()
    return {"id": category_id}
