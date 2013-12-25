function upvote(htmlId, id, voteBtn, type) {
    $.post('/upvote', {
        id: id,
        type: type
    }).done(function(updated) {
        // set the upvote value to it's updated value
        $(htmlId).text(updated['upvotes']);
    });

    // disable the vote buttons after voting on a post
    $(voteBtn).click(function(e) {
        e.preventDefault();
    });
}

function downvote(htmlId, id, voteBtn, type) {
    $.post('/downvote', {
        id: id,
        type: type
    }).done(function(updated) {
        $(htmlId).text(updated['downvotes']);
    });
    
    $(voteBtn).click(function(e) {
        e.preventDefault();
    });
}

function comment(postId) {
    $.post('/comment', {
        post_id: postId,
        text: $('textarea[name="comment_text"]').val()
    }).done(function(response) {
        var ul = document.getElementById("comment_list");
        var li = document.createElement("li");
        var comment = document.createElement("p");
        comment.innerHTML = $('textarea[name="comment_text"]').val();
        var hr = document.createElement("hr");
        hr.className = "divider";
        li.appendChild(comment);
        li.appendChild(hr);
        ul.insertBefore(li, ul.getElementsByTagName("li")[0]);
    });
}
