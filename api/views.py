from django.db import IntegrityError
from django.views.defaults import bad_request
from psycopg2.errors import UniqueViolation
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action, permission_classes
from rest_framework.exceptions import PermissionDenied, ParseError
from rest_framework.views import APIView
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import Book, BookRecord, BookReview
from .serializers import (
    BookSerializer,
    BookDetailSerializer,
    BookRecordSerializer,
    BookReviewSerializer,
)
from .custom_permissions import (
    IsAdminOrReadOnly,
    IsReaderOrReadOnly,
)
from api import serializers
from django.db.models import Count


class BookViewSet(ModelViewSet):
    queryset = Book.objects.all().order_by("title")
    serializer_class = BookDetailSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["list"]:
            return BookSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        # if there are query params, and there is a key for "search", use that search term to filter the queryset
        search_term = self.request.query_params.get("search")
        if search_term is not None:
            results = Book.objects.filter(
                title__icontains=self.request.query_params.get("search")
            )
        else:
            # if there is no query param, use the default queryset
            results = super().get_queryset()
        return results

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            error_data = {
                "error": "Unique constraint violation: there is already a book with this title by this author."
            }
            return Response(error_data, status=400)

    @action(detail=False)
    def featured(self, request):
        featured_books = Book.objects.filter(featured=True)
        serializer = self.get_serializer(featured_books, many=True)
        return Response(serializer.data)

    @action(detail=False)
    def favorites(self, request):
        favorited_books = request.user.favorite_books.all()
        serializer = self.get_serializer(favorited_books, many=True)
        return Response(serializer.data)


class BookRecordViewSet(ModelViewSet):
    queryset = BookRecord.objects.all()
    serializer_class = BookRecordSerializer
    permission_classes = [IsAuthenticated, IsReaderOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(reader=self.request.user, book=self.kwargs["book_pk"])

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            error_data = {
                "error": "Unique constraint violation: this user has already created a book record for this book."
            }
            return Response(error_data, status=400)

    def perform_create(self, serializer):
        book = get_object_or_404(Book, pk=self.kwargs["book_pk"])
        serializer.save(reader=self.request.user, book=book)


class BookReviewDetailView(RetrieveDestroyAPIView):
    serializer_class = BookReviewSerializer
    queryset = BookReview.objects.all()


class BookReviewListCreateView(ListCreateAPIView):
    serializer_class = BookReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = BookReview.objects.filter(book_id=self.kwargs["book_pk"])
        search_term = self.request.query_params.get("search")
        if search_term is not None:
            ## this is using the search method for postgres full-text search
            queryset = queryset.filter(body__search=search_term)
        return queryset

    def perform_create(self, serializer, **kwargs):
        book = get_object_or_404(Book, pk=self.kwargs["book_pk"])
        serializer.save(reviewed_by=self.request.user, book=book)


class CreateFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        # I need to know the user
        user = self.request.user
        # I need to know the book
        book = get_object_or_404(Book, pk=self.kwargs["book_pk"])
        # I need to add the book to the user's favorites
        user.favorite_books.add(book)
        # use a serializer to serialize data about the book we just favorited
        serializer = BookDetailSerializer(book, context={"request": request})
        # return a response
        return Response(serializer.data, status=201)
