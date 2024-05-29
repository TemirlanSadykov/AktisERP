$("#menu-toggle").click(function (e) {
    e.preventDefault();
    $("#wrapper").toggleClass("toggled");
    const icon = $(this).find('.fa');
    if (icon.hasClass('fa-bars')) {
      icon.removeClass('fa-bars').addClass('fa-times');
    } else {
      icon.removeClass('fa-times').addClass('fa-bars');
    }
  });

  $("#close-sidebar").click(function (e) {
    e.preventDefault();
    $("#wrapper").removeClass("toggled");
    $("#menu-toggle .fa").removeClass('fa-times').addClass('fa-bars');
  });