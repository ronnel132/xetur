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

function createCommentDescrip(content, func_name, comment_id) {
    var p = document.createElement("p");
    p.innerHTML = content;
    p.className = "descrip_entity";
    p.id = "comment_".concat(func_name).concat(comment_id);
    return p;
}

function createCommentLink(content, comment_id) {
    var a = document.createElement("a");
    a.className = "descrip_entity votebtn".concat(comment_id);
    a.innerHTML = content;
    var func_name = content.toLowerCase();
    a.href = "javascript:".concat(func_name).concat('(').concat(
    "'#comment_").concat(func_name).concat(comment_id).concat(
    "', '").concat(comment_id).concat("', '.votebtn").concat(comment_id)
    .concat("', 'comment');");
    return a;
}

function comment(topic, postId) {
    $.post('/comment', {
        post_id: postId,
        text: $('textarea[name="comment_text"]').val(),
        topic: topic
    }).done(function(response) {
        if (response['authorized']) {
            if (response['success']) {
                var ul = document.getElementById("comment_list");
                var li = document.createElement("li");
                var comment = document.createElement("p");
                comment.innerHTML = $('textarea[name="comment_text"]').val();
                var comment_id = response['comment_id'];
                var submitted_by = document.createElement("p");
                submitted_by.innerHTML = "Submitted by ".concat(response['username']);
                submitted_by.className = "descrip_entity";
                var upvotes = createCommentDescrip('0', 'upvote', comment_id);
                var downvotes = createCommentDescrip('0', 'downvote', comment_id);
                var upvoteButton = createCommentLink('Upvote', comment_id);
                var downvoteButton = createCommentLink('Downvote', comment_id);
                var div = document.createElement("div");
                div.className = "post_descrip";
                li.appendChild(comment);

                
                div.appendChild(submitted_by);
                div.appendChild(upvotes);
                div.appendChild(upvoteButton);
                div.appendChild(downvotes);
                div.appendChild(downvoteButton);
                li.appendChild(div);
                
                var comment_div = document.createElement("div");
                comment_div.className = "comment_divider";
                li.appendChild(comment_div);

                li.style.display = "none";
                ul.insertBefore(li, ul.getElementsByTagName("li")[0]);
                $(li).fadeIn();
            }
        } 
        else {
            window.location.href = "/login";
        }
    });
}
