from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext


from app.models.user import User
from app.schemas.user import UserRegisterRequest, UserResponse
from app.schemas.token import Token
from app.core.security import verify_password, create_access_token

# Setup bcrypt for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(request: UserRegisterRequest):
    """
    Register a new user in the system.
    Ensures the email is unique before creating the account.
    """
    # 1. Check if user already exists
    existing_user = await User.find_one(User.email == request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered."
        )

    # 2. Hash the plain text password
    hashed_pwd = pwd_context.hash(request.password)

    # 3. Create a new user document
    new_user = User(
        email=request.email,
        hashed_password=hashed_pwd,
        full_name=request.full_name
    )
    
    # 4. Insert into MongoDB
    await new_user.insert()

    # 5. Return the response model (password is naturally excluded)
    return UserResponse(
        id=str(new_user.id),
        email=new_user.email,
        full_name=new_user.full_name,
        is_active=new_user.is_active
    )
@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return a JWT access token.
    Note: OAuth2 standard specifies 'username' as the field name, but we will pass the 'email' into it.
    """
    user = await User.find_one(User.email == form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return {"access_token": access_token, "token_type": "bearer"}

