drop table if exists comments;
drop table if exists posts;
drop table if exists users;
drop table if exists topics;

create table topics (
    topic varchar(30) primary key,
    description text not null
);

create table users (
    username varchar(25) primary key,
    salt char(8) not null,
    password_hash char(64) not null,
    upvotes integer default 0,
    downvotes integer default 0,
    signup_date timestamp default now() 
);

create table posts (
    post_id integer primary key auto_increment,
    time timestamp default current_timestamp,
    url text,
    topic varchar(30) not null references topics(topic),
    poster varchar(25) not null references users(username),
    subject text not null,
    body text
);

create table comments (
    comment_id integer primary key auto_increment, 
    time timestamp default current_timestamp,
    post_id integer not null references posts(post_id),
    poster varchar(25) not null references users(username),
    body text not null
);

insert into topics values ('science', 'Submissions and discussions on scientific topics.');
insert into topics values ('news', 'Current events around the world.');
insert into topics values ('gaming', 'A branch for anything related to videogames.');
insert into topics values ('funny', 'A place for humorous things.');
insert into topics values ('misc', 'Everything else.');
