from django.contrib.auth import get_user_model

User = get_user_model()

class AssignBranchMixin:
    def form_valid(self, form):
        response = super().form_valid(form)
        if hasattr(self.object, 'profile'):
            self.object.userprofile.branch = self.request.user.userprofile.branch
            self.object.userprofile.save()
        return response
    
class RestrictBranchMixin:
    """
    A mixin to restrict querysets in class-based views to the current user's branch.
    """
    def get_queryset(self):
        """
        Override the default queryset to filter by the user's associated branch.
        """
        queryset = super().get_queryset()
        return queryset.filter(branch=self.request.user.userprofile.branch)