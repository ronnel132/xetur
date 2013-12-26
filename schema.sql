drop table if exists comments;
drop table if exists posts;
drop table if exists users;
drop table if exists topics;

create table topics (
    topic text primary key
);

create table users (
    username text primary key,
    salt char(8) not null,
    password_hash char(64) not null,
    upvotes integer default 0,
    downvotes integer default 0,
    signup_date datetime default current_timestamp
);

create table posts (
    post_id integer primary key autoincrement,
    url text,
    topic text not null references topics(topic),
    poster text not null references users(username),
    subject text not null,
    body text
);

create table comments (
    comment_id integer primary key autoincrement, 
    post_id integer not null references posts(post_id),
    poster text not null references users(username),
    body text not null
);

insert into topics values ('science');
insert into topics values ('gaming');
insert into topics values ('funny');
insert into topics values ('misc');
