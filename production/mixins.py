from django.contrib.auth import get_user_model

User = get_user_model()

class AssignBranchMixin:
    def form_valid(self, form):
        response = super().form_valid(form)
        # Ensure the User object has a related UserProfile
        if hasattr(self.object, 'userprofile'):
            # Set the UserProfile's branch to the current user's branch
            self.object.userprofile.branch = self.request.user.userprofile.branch
            self.object.userprofile.save()
        return response
    
class RestrictBranchMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(branch=self.request.user.userprofile.branch)