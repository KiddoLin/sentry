import React from 'react';
import {isEqual} from 'lodash';

import {Team, Organization, Project} from 'app/types';
import getDisplayName from 'app/utils/getDisplayName';
import {Client} from 'app/api';

// We require these props when using this HOC
type DependentProps = {
  api: Client;
  organization: Organization;
  teams: Team[];
  loadingTeams: boolean;
};

type InjectedProjectsProps = {
  projects: Project[];
  loadingProjects: boolean;
};

type State = {
  projects: Project[];
  loadingProjects: boolean;
};

const withTeamProjects = <P extends InjectedProjectsProps>(
  WrappedComponent: React.ComponentType<P>
) =>
  class extends React.Component<
    Omit<P, keyof InjectedProjectsProps> &
      Partial<InjectedProjectsProps> &
      DependentProps,
    State
  > {
    static displayName = `withTeamProjects(${getDisplayName(WrappedComponent)})`;

    state = {
      projects: [],
      loadingProjects: true,
    };

    componentDidMount() {
      if (!this.props.loadingTeams) {
        this.fetchProjects();
      }
    }

    componentDidUpdate(prevProps) {
      if (!this.props.loadingTeams && !isEqual(prevProps.teams, this.props.teams)) {
        this.fetchProjects();
      }
    }

    fetchProjects() {
      this.setState({
        loadingProjects: true,
      });
      const promises = this.getTeamsProjectPromises();
      if (promises.length > 0) {
        Promise.all(promises).then(projects => {
          this.setState({
            projects: projects.flat(),
            loadingProjects: false,
          });
        });
      }
    }

    getTeamsProjectPromises() {
      return this.getTeamsProjectEndpoints().map(endpoint => {
        return this.props.api.requestPromise(endpoint);
      });
    }

    getTeamsProjectEndpoints() {
      return this.props.teams!.map(team => {
        return `/teams/${this.props.organization.slug}/${team.slug}/projects/`;
      });
    }

    render() {
      return (
        <WrappedComponent
          {...this.props as (P & DependentProps)}
          projects={this.state.projects as Project[]}
          loadingProjects={this.state.loadingProjects}
        />
      );
    }
  };

export default withTeamProjects;
